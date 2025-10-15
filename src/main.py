from logger import logger
import logging
import json
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
    # Get the project_id, status_field_id, and QA Testing option ID
    # ----------------------------------------------------------------------------------------

    project_title = config.project_title

    project_id = graphql.get_project_id_by_title(
        owner=config.repository_owner,
        project_title=project_title
    )

    if not project_id:
        logging.error(f"Project {project_title} not found.")
        return None

    status_field_id = graphql.get_status_field_id(
        project_id=project_id,
        status_field_name=config.status_field_name
    )

    if not status_field_id:
        logging.error(f"Status field not found in project {project_title}")
        return None

    status_option_id = graphql.get_qatesting_status_option_id(
        project_id=project_id,
        status_field_name=config.status_field_name
    )

    if not status_option_id:
        logging.error(f"'QA Testing' option not found in project {project_title}")
        return None

    # ----------------------------------------------------------------------------------------
    # Iterate over merged PRs and update linked issues
    # ----------------------------------------------------------------------------------------

    for pr in merged_prs:
        pr_number = pr["number"]
        pr_url = pr["url"]
        pr_title = pr["title"]
        linked_issues = pr.get("referencedIssues", {}).get("nodes", [])

        if not linked_issues:
            logger.info(f"PR #{pr_number} ({pr_title}) has no linked issues.")
            continue

        logger.info(f"Processing PR #{pr_number} with {len(linked_issues)} linked issue(s).")

        for issue in linked_issues:
            issue_id = issue["id"]
            issue_number = issue["number"]

            comment_text = (
                f"Testing will be available in 15 minutes "
                f"(triggered by [PR #{pr_number}]({pr_url}))"
            )

            # Skip if comment already exists
            if check_comment_exists(issue_id, comment_text):
                logger.info(f"Skipping issue #{issue_number} — comment already exists for PR #{pr_number}.")
                continue

            # Fetch the current status of the issue
            current_status = graphql.get_issue_status(issue_id, config.status_field_name)

            # Always attempt to find the project item dynamically
            item_id = graphql.get_project_item_id_for_issue(project_id, issue_id)

            if not item_id:
                logger.warning(f"No project item found for issue #{issue_number}. Skipping.")
                continue

            if current_status != "QA Testing":
                logger.info(f"Updating issue #{issue_number} to QA Testing (triggered by PR #{pr_number}).")

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
                # Already QA Testing → just add new comment
                logger.info(f"Issue #{issue_number} already in QA Testing → adding comment for PR #{pr_number}.")
                graphql.add_issue_comment(issue_id, comment_text)


def main():
    logger.info("🔄 Process started...")
    if config.dry_run:
        logger.info("DRY RUN MODE ON!")

    notify_change_status()


if __name__ == "__main__":
    main()
