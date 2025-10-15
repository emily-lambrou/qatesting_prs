from pprint import pprint
import logging
import requests
import config

logging.basicConfig(level=logging.DEBUG)


def get_recent_merged_prs_in_dev(owner, repo, since_timestamp=None):
    """
    Fetch all merged PRs in the 'dev' branch (optionally after a given date).
    Uses 'referencedIssues' to capture all issues mentioned with '#' in the PR body.
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
            referencedIssues(first: 10) {
              nodes {
                id
                number
                title
                url
              }
            }
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

            nodes = (
                data.get("data", {})
                .get("repository", {})
                .get("pullRequests", {})
                .get("nodes", [])
            )
            for pr in nodes:
                if since_timestamp and pr["mergedAt"] < since_timestamp:
                    continue
                prs.append(pr)

            page_info = (
                data.get("data", {})
                .get("repository", {})
                .get("pullRequests", {})
                .get("pageInfo", {})
            )
            if not page_info.get("hasNextPage"):
                break
            variables["afterCursor"] = page_info.get("endCursor")
        return prs
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
        projects = (
            data.get("data", {})
            .get("organization", {})
            .get("projectsV2", {})
            .get("nodes", [])
        )
        for project in projects:
            if project.get("title") == project_title:
                return project.get("id")
        return None
    except requests.RequestException as e:
        logging.error(f"Request error: {e}")
        return None


def get_status_field_id(project_id, status_field_name):
    """
    Returns the ID of the 'Status' field in the specified project.
    Now handles cases where nodes lack a 'name' key safely.
    """
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
        fields = (
            data.get("data", {}).get("node", {}).get("fields", {}).get("nodes", [])
        )
        for field in fields:
            if (
                field.get("__typename") == "ProjectV2SingleSelectField"
                and field.get("name") == status_field_name
            ):
                return field.get("id")
        return None
    except requests.RequestException as e:
        logging.error(f"Request error: {e}")
        return None


def get_qatesting_status_option_id(project_id, status_field_name):
    """
    Returns the option ID for 'QA Testing' within the project's Status field.
    Includes safe access and null checks.
    """
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
        fields = (
            data.get("data", {}).get("node", {}).get("fields", {}).get("nodes", [])
        )
        for field in fields:
            if (
                field.get("__typename") == "ProjectV2SingleSelectField"
                and field.get("name") == status_field_name
            ):
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
        nodes = (
            data.get("data", {}).get("node", {}).get("projectItems", {}).get("nodes", [])
        )
        for item in nodes:
            field = item.get("fieldValueByName")
            if field:
                return field.get("name")
        return None
    except requests.RequestException as e:
        logging.error(f"Request error: {e}")
        return None


def get_project_item_id_for_issue(project_id, issue_id):
    """
    Returns the Project Item ID for a given issue ID inside the specified project.
    """
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
        items = (
            data.get("data", {}).get("node", {}).get("projectItems", {}).get("nodes", [])
        )
        for item in items:
            project = item.get("project", {})
            if project and project.get("id") == project_id:
                return item.get("id")
        return None
    except requests.RequestException as e:
        logging.error(f"Request error: {e}")
        return None


def update_issue_status_to_qa_testing(
    owner, project_title, project_id, status_field_id, item_id, status_option_id
):
    mutation = """
    mutation UpdateIssueStatus($projectId: ID!, $itemId: ID!, $statusFieldId: ID!, $statusOptionId: String!) {
      updateProjectV2ItemFieldValue(input: {
        projectId: $projectId,
        itemId: $itemId,
        fieldId: $statusFieldId,
        value: { singleSelectOptionId: $statusOptionId }
      }) {
        projectV2Item { id }
      }
    }
    """
    variables = {
        "projectId": project_id,
        "itemId": item_id,
        "statusFieldId": status_field_id,
        "statusOptionId": status_option_id,
    }
    try:
        response = requests.post(
            config.api_endpoint,
            json={"query": mutation, "variables": variables},
            headers={"Authorization": f"Bearer {config.gh_token}"},
        )
        return response.json().get("data")
    except requests.RequestException as e:
        logging.error(f"Request error: {e}")
        return None


def get_issue_comments(issue_id):
    query = """
    query GetIssueComments($issueId: ID!, $afterCursor: String) {
      node(id: $issueId) {
        ... on Issue {
          comments(first: 100, after: $afterCursor) {
            nodes {
              body
              createdAt
            }
            pageInfo {
              endCursor
              hasNextPage
            }
          }
        }
      }
    }
    """
    variables = {"issueId": issue_id, "afterCursor": None}
    comments = []
    try:
        while True:
            response = requests.post(
                config.api_endpoint,
                json={"query": query, "variables": variables},
                headers={"Authorization": f"Bearer {config.gh_token}"},
            )
            data = response.json()
            nodes = (
                data.get("data", {})
                .get("node", {})
                .get("comments", {})
                .get("nodes", [])
            )
            comments.extend(nodes)
            page = (
                data.get("data", {})
                .get("node", {})
                .get("comments", {})
                .get("pageInfo", {})
            )
            if not page.get("hasNextPage"):
                break
            variables["afterCursor"] = page.get("endCursor")
        return comments
    except requests.RequestException as e:
        logging.error(f"Request error: {e}")
        return []


def add_issue_comment(issue_id, body: str):
    mutation = """
    mutation AddComment($subjectId: ID!, $body: String!) {
      addComment(input: {subjectId: $subjectId, body: $body}) {
        commentEdge {
          node { id body }
        }
      }
    }
    """
    variables = {"subjectId": issue_id, "body": body}
    try:
        response = requests.post(
            config.api_endpoint,
            json={"query": mutation, "variables": variables},
            headers={"Authorization": f"Bearer {config.gh_token}"},
        )
        return response.json().get("data")
    except requests.RequestException as e:
        logging.error(f"Request error: {e}")
        return None
