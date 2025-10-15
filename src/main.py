from logger import logger
import logging
import config
import graphql
import re


def parse_issue_references(text):
    """
    Extracts same-repo and cross-repo issue references.
    Matches patterns like:
    - #123
    - RepoName#123
    - OrgName/RepoName#123
    """
    pattern = r'(?:(?:(?P<org>[\w-]+)/)?(?P<repo>[\w-]+))?#(?P<number>\d+)'
    matches = re.finditer(pattern, text or "")
    issues = []

    for match in matches:
        org = match.group("org") or config.repository_owner
        repo = match.group("repo")
        number = match.group("number")

        # Handle plain "#123" (same repo)
        if repo is None:
            repo = config.repository_name

        issues.append({
            "org": org,
            "repo": repo,
            "number": int(number)
        })

    return issues


def check_comment_exists(issue_id, comment_text):
    """Check if the comment already exists on the issue."""
    comments = graphql.get_issue_comments(issue_id)
    for comment in comments:
        if comment_text in comment.get("body", ""):
            return True
    return False


def notify_change_status():
    logger.info("Fetching merged PRs into dev...")

    merged_prs = graphql.get_recent_merged_prs_in_dev(
        owner=config.repository_owner,
        repo=config.repository_name
    )

    if not merged_prs:
        logger.info("No merged PRs found in dev.")
        return

    project_title = config.project_title

    project_id = graphql.get_project_id_by_title(
        owner=config.repository_owner,
        project_title=project_title
    )
    if not project_id:
        logging.error(f"Project {project_title} not found.")
        return

    status_field_id = graphql.get_status_field_id(
        project_id=project_id,
        status_field_name=config.status_field_name
    )
    if not status_field_id:
        logging.error(f"Status field not found in project {project_title}")
        return

    status_option_id = graphql.get_qatesting_status_option_id(
        project_id=project_id,
        status_field_name=config.status_field_name
    )
    if not status_option_id:
        logging.error(f"'QA Testing' option not found in project {project_title}")
        return

    # ----------------------------------------------------------------------
    # Process each merged PR and detect mentioned issues in the body text
    # ----------------------------------------------------------------------

    for pr in merged_prs:
        pr_number = pr["number"]
        pr_url = pr["url"]
        pr_title = pr["title"]
        pr_body = pr.get("bodyText") or ""

        logger.info(f"Checking PR #{pr_number} ({pr_title}) for mentioned issues in description...")

        mentioned_issues = parse_issue_references(pr_body)
        if not mentioned_issues:
            logger.info(f"PR #{pr_number} has no mentioned issues in description.")
            continue

        for ref in mentioned_issues:
            issue_owner = ref["org"]
            issue_repo = ref["repo"]
            issue_number = ref["number"]

            issue_id = graphql.get_issue_id_by_number(issue_owner, issue_repo, issue_number)
            if not issue_id:
                logger.warning(f"Issue {issue_owner}/{issue_repo}#{issue_number} not found.")
                continue

            comment_text = (
                f"Testing will be available in 15 minutes "
                f"(triggered by [PR #{pr_number}]({pr_url}))"
            )

            if check_comment_exists(issue_id, comment_text):
                logger.info(f"Skipping {issue_owner}/{issue_repo}#{issue_number} — comment already exists.")
                continue

            current_status = graphql.get_issue_status(issue_id, config.status_field_name)

            if current_status != "QA Testing":
                logger.info(f"Updating {issue_owner}/{issue_repo}#{issue_number} to QA Testing (PR #{pr_number}).")

                update_result = graphql.update_issue_status_to_qa_testing(
                    owner=issue_owner,
                    project_title=project_title,
                    project_id=project_id,
                    status_field_id=status_field_id,
                    item_id=None,  # Project item ID not required; GraphQL infers it
                    status_option_id=status_option_id,
                    issue_id=issue_id
                )

                if update_result:
                    logger.info(f"✅ Successfully updated {issue_owner}/{issue_repo}#{issue_number} to QA Testing.")
                    graphql.add_issue_comment(issue_id, comment_text)
                else:
                    logger.error(f"❌ Failed to update {issue_owner}/{issue_repo}#{issue_number}.")
            else:
                logger.info(f"Issue {issue_owner}/{issue_repo}#{issue_number} already in QA Testing → adding comment.")
                graphql.add_issue_comment(issue_id, comment_text)


def main():
    logger.info("🔄 Process started...")
    if config.dry_run:
        logger.info("DRY RUN MODE ON!")

    notify_change_status()


if __name__ == "__main__":
    main()
