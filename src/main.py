from logger import logger
import logging
import config
import graphql


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

    # ----------------------------------------------------------------------------------------
    # Get project and status metadata
    # ----------------------------------------------------------------------------------------
    project_title = config.project_title

    project_id = graphql.get_project_id_by_title(
        owner=config.repository_owner,
        project_title=project_title
    )
    if not project_id:
        logging.error(f"Project {project_title} not found.")
        return None

    status_field_id = graphql.get_status_field_id(project_id, config.status_field_name)
    if not status_field_id:
        logging.error(f"Status field not found in project {project_title}")
        return None

    status_option_id = graphql.get_qatesting_status_option_id(project_id, config.status_field_name)
    if not status_option_id:
        logging.error(f"'QA Testing' option not found in project {project_title}")
        return None

    # ----------------------------------------------------------------------------------------
    # Iterate over merged PRs and update linked issues
    # ----------------------------------------------------------------------------------------
    for pr in merged_prs:
        pr_id = pr["id"]
        pr_number = pr["number"]
        pr_title = pr["title"]
        pr_url = pr["url"]

        logger.info(f"Checking PR #{pr_number} ({pr_title}) for mentioned issues in description...")

        linked_issues = graphql.get_issues_from_pr_description(pr_id)

        if not linked_issues:
            logger.info(f"PR #{pr_number} has no mentioned issues in description.")
            continue

        logger.info(f"Processing PR #{pr_number} with {len(linked_issues)} linked issue(s).")

        for issue in linked_issues:
            issue_id = issue["id"]
            issue_number = issue["number"]

            comment_text = f"Testing will be available in 15 minutes (triggered by [PR #{pr_number}]({pr_url}))"

            if check_comment_exists(issue_id, comment_text):
                logger.info(f"Skipping issue #{issue_number} — comment already exists.")
                continue

            current_status = graphql.get_issue_status(issue_id, config.status_field_name)
            item_id = graphql.get_project_item_id_for_issue(project_id, issue_id)

            if not item_id:
                logger.warning(f"Issue #{issue_number} not linked to project {project_title}.")
                continue

            if current_status != "QA Testing":
                logger.info(f"Updating issue #{issue_number} to QA Testing.")
                update_result = graphql.update_issue_status_to_qa_testing(
                    owner=config.repository_owner,
                    project_title=project_title,
                    project_id=project_id,
                    status_field_id=status_field_id,
                    item_id=item_id,
                    status_option_id=status_option_id,
                )

                if update_result:
                    logger.info(f"✅ Successfully updated issue #{issue_number} to QA Testing.")
                    graphql.add_issue_comment(issue_id, comment_text)
                else:
                    logger.error(f"❌ Failed to update issue #{issue_number}.")
            else:
                logger.info(f"Issue #{issue_number} already in QA Testing — adding comment only.")
                graphql.add_issue_comment(issue_id, comment_text)


def main():
    logger.info("🔄 Process started...")
    if config.dry_run:
        logger.info("DRY RUN MODE ON!")
    notify_change_status()


if __name__ == "__main__":
    main()
