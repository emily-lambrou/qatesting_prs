from pprint import pprint
import logging
import requests
import config

logging.basicConfig(level=logging.DEBUG)


def get_recent_merged_prs_in_dev(owner, repo, since_timestamp=None):
    """
    Fetch all merged PRs in the 'dev' branch (optionally after a given date).
    """
    query = """
    query GetMergedPRs($owner: String!, $repo: String!, $afterCursor: String) {
      repository(owner: $owner, name: $repo) {
        pullRequests(
          first: 100
          after: $afterCursor
          baseRefName: "dev"
          states: MERGED
          orderBy: {field: UPDATED_AT, direction: DESC}
        ) {
          nodes {
            id
            number
            title
            mergedAt
            url
            bodyText
          }
          pageInfo {
            endCursor
            hasNextPage
          }
        }
      }
    }
    """
    variables = {"owner": owner, "repo": repo, "afterCursor": None}
    prs = []
    try:
        while True:
            response = requests.post(
                config.api_endpoint,
                json={"query": query, "variables": variables},
                headers={"Authorization": f"Bearer {config.gh_token}"},
            )
            data = response.json()
            if "errors" in data:
                logging.error(f"GraphQL query errors: {data['errors']}")
                break

            nodes = data.get("data", {}).get("repository", {}).get("pullRequests", {}).get("nodes", [])
            for pr in nodes:
                if since_timestamp and pr["mergedAt"] < since_timestamp:
                    continue
                prs.append(pr)

            page_info = data.get("data", {}).get("repository", {}).get("pullRequests", {}).get("pageInfo", {})
            if not page_info.get("hasNextPage"):
                break
            variables["afterCursor"] = page_info.get("endCursor")
        return prs
    except requests.RequestException as e:
        logging.error(f"Request error: {e}")
        return []


def get_issues_from_pr_description(pr_id):
    """
    Finds issues mentioned in the PR description using CrossReferencedEvent in PR timeline.
    Works when issue numbers are mentioned in PR body (e.g., "Fixes #123" or "Related to #456").
    """
    query = """
    query($prId: ID!, $after: String) {
      node(id: $prId) {
        ... on PullRequest {
          timelineItems(first: 100, after: $after) {
            nodes {
              __typename
              ... on CrossReferencedEvent {
                target {
                  __typename
                  ... on Issue {
                    id
                    number
                    title
                    url
                  }
                }
              }
            }
            pageInfo {
              hasNextPage
              endCursor
            }
          }
        }
      }
    }
    """

    issues = []
    variables = {"prId": pr_id, "after": None}

    try:
        while True:
            response = requests.post(
                config.api_endpoint,
                json={"query": query, "variables": variables},
                headers={"Authorization": f"Bearer {config.gh_token}"},
            )
            data = response.json()
            if "errors" in data:
                logging.error(f"GraphQL query errors: {data['errors']}")
                break

            nodes = data.get("data", {}).get("node", {}).get("timelineItems", {}).get("nodes", [])
            for node in nodes:
                if node.get("__typename") == "CrossReferencedEvent":
                    target = node.get("target")
                    if target and target.get("__typename") == "Issue":
                        issues.append(target)

            page_info = data.get("data", {}).get("node", {}).get("timelineItems", {}).get("pageInfo", {})
            if not page_info.get("hasNextPage"):
                break
            variables["after"] = page_info.get("endCursor")

        return issues
    except requests.RequestException as e:
        logging.error(f"Request error: {e}")
        return []


def get_project_id_by_title(owner, project_title):
    query = """
    query($owner: String!, $projectTitle: String!) {
      organization(login: $owner) {
        projectsV2(first: 10, query: $projectTitle) {
          nodes {
            id
            title
          }
        }
      }
    }
    """
    variables = {"owner": owner, "projectTitle": project_title}
    try:
        response = requests.post(
            config.api_endpoint,
            json={"query": query, "variables": variables},
            headers={"Authorization": f"Bearer {config.gh_token}"},
        )
        data = response.json()
        projects = data.get("data", {}).get("organization", {}).get("projectsV2", {}).get("nodes", [])
        for project in projects:
            if project.get("title") == project_title:
                return project.get("id")
        return None
    except requests.RequestException as e:
        logging.error(f"Request error: {e}")
        return None


def get_status_field_id(project_id, status_field_name):
    query = """
    query($projectId: ID!) {
      node(id: $projectId) {
        ... on ProjectV2 {
          fields(first: 100) {
            nodes {
              __typename
              ... on ProjectV2SingleSelectField {
                id
                name
              }
            }
          }
        }
      }
    }
    """
    variables = {"projectId": project_id}
    try:
        response = requests.post(
            config.api_endpoint,
            json={"query": query, "variables": variables},
            headers={"Authorization": f"Bearer {config.gh_token}"},
        )
        data = response.json()
        fields = data.get("data", {}).get("node", {}).get("fields", {}).get("nodes", [])
        for field in fields:
            if field.get("name") == status_field_name:
                return field.get("id")
        return None
    except requests.RequestException as e:
        logging.error(f"Request error: {e}")
        return None


def get_qatesting_status_option_id(project_id, status_field_name):
    query = """
    query($projectId: ID!) {
      node(id: $projectId) {
        ... on ProjectV2 {
          fields(first: 100) {
            nodes {
              ... on ProjectV2SingleSelectField {
                id
                name
                options {
                  id
                  name
                }
              }
            }
          }
        }
      }
    }
    """
    variables = {"projectId": project_id}
    try:
        response = requests.post(
            config.api_endpoint,
            json={"query": query, "variables": variables},
            headers={"Authorization": f"Bearer {config.gh_token}"},
        )
        data = response.json()
        fields = data.get("data", {}).get("node", {}).get("fields", {}).get("nodes", [])
        for field in fields:
            if field.get("name") == status_field_name:
                for option in field.get("options", []):
                    if option.get("name") == "QA Testing":
                        return option.get("id")
        return None
    except requests.RequestException as e:
        logging.error(f"Request error: {e}")
        return None


def get_issue_status(issue_id, status_field_name):
    query = """
    query($issueId: ID!, $statusField: String!) {
      node(id: $issueId) {
        ... on Issue {
          projectItems(first: 10) {
            nodes {
              fieldValueByName(name: $statusField) {
                ... on ProjectV2ItemFieldSingleSelectValue {
                  name
                }
              }
            }
          }
        }
      }
    }
    """
    variables = {"issueId": issue_id, "statusField": status_field_name}
    try:
        response = requests.post(
            config.api_endpoint,
            json={"query": query, "variables": variables},
            headers={"Authorization": f"Bearer {config.gh_token}"},
        )
        data = response.json()
        nodes = data.get("data", {}).get("node", {}).get("projectItems", {}).get("nodes", [])
        for item in nodes:
            field = item.get("fieldValueByName")
            if field:
                return field.get("name")
        return None
    except requests.RequestException as e:
        logging.error(f"Request error: {e}")
        return None


def get_project_item_id_for_issue(project_id, issue_id):
    query = """
    query($projectId: ID!, $issueId: ID!) {
      node(id: $issueId) {
        ... on Issue {
          projectItems(first: 10) {
            nodes {
              id
              project {
                id
              }
            }
          }
        }
      }
    }
    """
    variables = {"projectId": project_id, "issueId": issue_id}
    try:
        response = requests.post(
            config.api_endpoint,
            json={"query": query, "variables": variables},
            headers={"Authorization": f"Bearer {config.gh_token}"},
        )
        data = response.json()
        items = data.get("data", {}).get("node", {}).get("projectItems", {}).get("nodes", [])
        for item in items:
            project = item.get("project", {})
            if project and project.get("id") == project_id:
                return item.get("id")
        return None
    except requests.RequestException as e:
        logging.error(f"Request error: {e}")
        return None


def update_issue_status_to_qa_testing(owner, project_title, projec
