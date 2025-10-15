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
    # Fetch issues based on whether it's an enterprise or not
    if config.is_enterprise:
        issues = graphql.get_project_issues(
            owner=config.repository_owner,
            owner_type=config.repository_owner_type,
            project_number=config.project_number,
            status_field_name=config.status_field_name,
            filters={"open_only": True},
        )
    else:
        issues = graphql.get_repo_issues(
            owner=config.repository_owner, repository=config.repository_name
        )

    if not issues:
        logger.info("No issues have been found")
        return

    project_title = config.project_title
    project_id = graphql.get_project_id_by_title(
        owner=config.repository_owner, project_title=project_title
    )
    if not project_id:
        logging.error(f"Project {project_title} not found.")
        return None

    status_field_id = graphql.get_status_field_id(
        project_id=project_id, status_field_name=config.status_field_name
    )
    if not status_field_id:
        logging.error(f"Status field not found in project {project_title}")
        return None

    status_option_id = graphql.get_qatesting_status_option_id(
        project_id=project_id, status_field_name=config.status_field_name
    )
    if not status_option_id:
        logging.error(f"'QA Testing' option not found in project {project_title}")
        return None

    items = graphql.get_project_items(
        owner=config.repository_owner,
        owner_type=config.repository_owner_type,
        project_number=config.project_number,
        status_field_name=config.status_field_name,
    )

    for issue in issues:
        if issue.get("state") == "CLOSED":
            continue

        issue_content = issue.get("content", {})
        if not issue_content:
            continue

        issue_id = issue_content.get("id")
        if not issue_id:
            continue

        field_value = issue.get("fieldValueByName")
        current_status = field_value.get("name") if field_value else None

        latest_pr = graphql.get_latest_merged_pr_into_dev(issue_id)
        if not latest_pr:
            continue

        pr_number = latest_pr["number"]
        pr_url = latest_pr["url"]

        comment_text = (
            f"Testing will be available in 15 minutes "
            f"(triggered by [PR #{pr_number}]({pr_url}))"
        )

        # Skip if comment for this PR already exists
        if check_comment_exists(issue_id, comment_text):
            continue

        if current_status != "QA Testing":
            # Update status to QA Testing
            logger.info(
                f"Updating issue {issue_id} to QA Testing (triggered by PR #{pr_number})"
            )

            item_found = False
            for item in items:
                if item.get("content") and item["content"].get("id") == issue_id:
                    item_id = item["id"]
                    item_found = True

                    update_result = graphql.update_issue_status_to_qa_testing(
                        owner=config.repository_owner,
                        project_title=project_title,
                        project_id=project_id,
                        status_field_id=status_field_id,
                        item_id=item_id,
                        status_option_id=status_option_id,
                    )

                    if update_result:
                        logger.info(
                            f"Successfully updated issue {issue_id} to QA Testing."
                        )
                        graphql.add_issue_comment(issue_id, comment_text)
                    else:
                        logger.error(f"Failed to update issue {issue_id}.")
                    break

            if not item_found:
                logger.warning(f"No matching item found for issue ID: {issue_id}.")
                continue
        else:
            # Already QA → just drop a new comment for the new PR
            logger.info(
                f"Issue {issue_id} already QA Testing → adding new comment for PR #{pr_number}"
            )
            graphql.add_issue_comment(issue_id, comment_text)


def main():
    logger.info("Process started...")
    if config.dry_run:
        logger.info("DRY RUN MODE ON!")

    notify_change_status()


if __name__ == "__main__":
    main()
