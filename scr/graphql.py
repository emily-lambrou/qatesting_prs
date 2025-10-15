from pprint import pprint
import logging
import requests
import config

logging.basicConfig(level=logging.DEBUG)  # Ensure logging is set up


def get_repo_issues(owner, repository, after=None, issues=None):
    query = """
    query GetRepoClosedIssues($owner: String!, $repo: String!, $after: String) {
      repository(owner: $owner, name: $repo) {
        issues(first: 100, after: $after, states: [OPEN]) {
          nodes {
            id
            title
            number
            url
            assignees(first:100) {
              nodes {
                name
                email
                login
              }
            }
            projectItems(first: 10) {
              nodes {
                project {
                  number
                  title
                }
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
    variables = {"owner": owner, "repo": repository, "after": after}
    response = requests.post(
        config.api_endpoint,
        json={"query": query, "variables": variables},
        headers={"Authorization": f"Bearer {config.gh_token}"},
    )
    data = response.json()
    if data.get("errors"):
        print(data.get("errors"))
    pprint(data)
    repository_data = data.get("data", {}).get("repository", {})
    issues_data = repository_data.get("issues", {})
    pageinfo = issues_data.get("pageInfo", {})
    nodes = issues_data.get("nodes", [])
    if issues is None:
        issues = []
    issues = issues + nodes
    if pageinfo.get("hasNextPage"):
        return get_repo_issues(
            owner, repository, after=pageinfo.get("endCursor"), issues=issues
        )
    return issues


def get_project_issues(
    owner, owner_type, project_number, status_field_name, filters=None, after=None, issues=None
):
    query = f"""
    query GetProjectIssues($owner: String!, $projectNumber: Int!, $status: String!, $after: String) {{
      {owner_type}(login: $owner) {{
        projectV2(number: $projectNumber) {{
          id
          title
          items(first: 100, after: $after) {{
            nodes {{
              id
              fieldValueByName(name: $status) {{
                ... on ProjectV2ItemFieldSingleSelectValue {{
                  id
                  name
                }}
              }}
              content {{
                ... on Issue {{
                  id
                  title
                  number
                  state
                  url
                }}
              }}
            }}
            pageInfo {{
              endCursor
              hasNextPage
            }}
          }}
        }}
      }}
    }}
    """
    variables = {
        "owner": owner,
        "projectNumber": project_number,
        "status": status_field_name,
        "after": after,
    }
    try:
        response = requests.post(
            config.api_endpoint,
            json={"query": query, "variables": variables},
            headers={"Authorization": f"Bearer {config.gh_token}"},
        )
        data = response.json()
        if "errors" in data:
            logging.error(f"GraphQL query errors: {data['errors']}")
            return []
        owner_data = data["data"].get(owner_type, {})
        project_data = owner_data.get("projectV2", {})
        items_data = project_data.get("items", {})
        pageinfo = items_data.get("pageInfo", {})
        nodes = items_data.get("nodes", [])
        if issues is None:
            issues = []
        if filters:
            filtered = []
            for node in nodes:
                issue_content = node.get("content", {})
                if not issue_content:
                    continue
                if filters.get("open_only") and issue_content.get("state") != "OPEN":
                    continue
                filtered.append(node)
            nodes = filtered
        issues = issues + nodes
        if pageinfo.get("hasNextPage"):
            return get_project_issues(
                owner,
                owner_type,
                project_number,
                status_field_name,
                filters,
                after=pageinfo.get("endCursor"),
                issues=issues,
            )
        return issues
    except requests.RequestException as e:
        logging.error(f"Request error: {e}")
        return []


def get_project_items(
    owner, owner_type, project_number, status_field_name, filters=None, after=None, items=None
):
    query = f"""
    query GetProjectItems($owner: String!, $projectNumber: Int!, $status: String!, $after: String) {{
      {owner_type}(login: $owner) {{
        projectV2(number: $projectNumber) {{
          id
          title
          items(first: 100, after: $after) {{
            nodes {{
              id
              fieldValueByName(name: $status) {{
                ... on ProjectV2ItemFieldSingleSelectValue {{
                  id
                  name
                }}
              }}
              content {{
                ... on Issue {{
                  id
                  title
                  state
                  url
                }}
              }}
            }}
            pageInfo {{
              endCursor
              hasNextPage
            }}
          }}
        }}
      }}
    }}
    """
    variables = {
        "owner": owner,
        "projectNumber": project_number,
        "status": status_field_name,
        "after": after,
    }
    try:
        response = requests.post(
            config.api_endpoint,
            json={"query": query, "variables": variables},
            headers={"Authorization": f"Bearer {config.gh_token}"},
        )
        data = response.json()
        if "errors" in data:
            logging.error(f"GraphQL query errors: {data['errors']}")
            return []
        owner_data = data["data"].get(owner_type, {})
        project_data = owner_data.get("projectV2", {})
        items_data = project_data.get("items", {})
        pageinfo = items_data.get("pageInfo", {})
        nodes = items_data.get("nodes", [])
        if items is None:
            items = []
        items += nodes
        if pageinfo.get("hasNextPage"):
            return get_project_items(
                owner,
                owner_type,
                project_number,
                status_field_name,
                filters,
                after=pageinfo.get("endCursor"),
                items=items,
            )
        return items
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
        if "errors" in data:
            logging.error(f"GraphQL query errors: {data['errors']}")
            return None
        projects = data["data"]["organization"]["projectsV2"]["nodes"]
        for project in projects:
            if project["title"] == project_title:
                return project["id"]
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
                options {
                  id
                  name
                }}
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
        if "errors" in data:
            logging.error(f"GraphQL query errors: {data['errors']}")
            return None
        fields = data["data"]["node"]["fields"]["nodes"]
        for field in fields:
            if (
                field.get("name") == status_field_name
                and field["__typename"] == "ProjectV2SingleSelectField"
            ):
                return field["id"]
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
              __typename
              ... on ProjectV2SingleSelectField {
                id
                name
                options {
                  id
                  name
                }}
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
        if "errors" in data:
            logging.error(f"GraphQL query errors: {data['errors']}")
            return None
        fields = data["data"]["node"]["fields"]["nodes"]
        for field in fields:
            if (
                field.get("name") == status_field_name
                and field["__typename"] == "ProjectV2SingleSelectField"
            ):
                for option in field.get("options", []):
                    if option["name"] == "QA Testing":
                        return option["id"]
        return None
    except requests.RequestException as e:
        logging.error(f"Request error: {e}")
        return None


def get_latest_merged_pr_into_dev(issue_id: str):
    """
    Returns the latest merged PR into dev for the given issue, or None if none exist.
    """
    query = """
    query GetIssueTimeline($issueId: ID!, $afterCursor: String) {
      node(id: $issueId) {
        ... on Issue {
          timelineItems(first: 100, after: $afterCursor) {
            nodes {
              __typename
              ... on CrossReferencedEvent {
                source {
                  ... on PullRequest {
                    id
                    number
                    mergedAt
                    url
                    baseRefName
                    headRefName
                  }
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
    }
    """
    variables = {"issueId": issue_id, "afterCursor": None}
    latest_pr = None
    try:
        while True:
            response = requests.post(
                config.api_endpoint,
                json={"query": query, "variables": variables},
                headers={
                    "Authorization": f"Bearer {config.gh_token}",
                    "Accept": "application/vnd.github.v4+json",
                },
            )
            data = response.json()
            if "errors" in data:
                logging.error(f"GraphQL query errors: {data['errors']}")
                return None

            timeline = data.get("data", {}).get("node", {}).get("timelineItems", {})
            nodes = timeline.get("nodes", [])
            for item in nodes:
                if item.get("__typename") == "CrossReferencedEvent":
                    pr = item.get("source")
                    if (
                        isinstance(pr, dict)
                        and pr.get("mergedAt")
                        and pr.get("baseRefName") == "dev"
                    ):
                        if latest_pr is None or pr["mergedAt"] > latest_pr["mergedAt"]:
                            latest_pr = {
                                "number": pr["number"],
                                "url": pr["url"],
                                "mergedAt": pr["mergedAt"],
                            }

            page = timeline.get("pageInfo", {})
            if not page.get("hasNextPage"):
                break
            variables["afterCursor"] = page.get("endCursor")

        return latest_pr
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
        data = response.json()
        if "errors" in data:
            logging.error(f"GraphQL mutation errors: {data['errors']}")
            return None
        return data.get("data")
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
              author { login }
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
    all_comments = []
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
            comments_data = data.get("data", {}).get("node", {}).get("comments", {})
            nodes = comments_data.get("nodes", [])
            all_comments.extend(nodes)
            page = comments_data.get("pageInfo", {})
            if not page.get("hasNextPage"):
                break
            variables["afterCursor"] = page.get("endCursor")
        return all_comments
    except requests.RequestException as e:
        logging.error(f"Request error: {e}")
        return []


def add_issue_comment(issue_id, body: str):
    """
    Adds a comment to the given issue.
    """
    mutation = """
    mutation AddComment($subjectId: ID!, $body: String!) {
      addComment(input: {subjectId: $subjectId, body: $body}) {
        commentEdge {
          node {
            id
            body
          }
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
        data = response.json()
        if "errors" in data:
            logging.error(f"GraphQL mutation errors: {data['errors']}")
            return None
        return data.get("data")
    except requests.RequestException as e:
        logging.error(f"Request error: {e}")
        return None
