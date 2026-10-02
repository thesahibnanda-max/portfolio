from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class _GitHubModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", validate_by_alias=True, validate_by_name=True)


class GitHubUserPlan(_GitHubModel):
    collaborators: int | None = None
    name: str | None = None
    space: int | None = None
    private_repos: int | None = None


class GitHubUser(_GitHubModel):
    login: str | None = None
    id: int | None = None
    node_id: str | None = None
    avatar_url: str | None = None
    gravatar_id: str | None = None
    url: str | None = None
    html_url: str | None = None
    followers_url: str | None = None
    following_url: str | None = None
    gists_url: str | None = None
    starred_url: str | None = None
    subscriptions_url: str | None = None
    organizations_url: str | None = None
    repos_url: str | None = None
    events_url: str | None = None
    received_events_url: str | None = None
    type: str | None = None
    user_view_type: str | None = None
    site_admin: bool | None = None
    name: str | None = None
    company: str | None = None
    blog: str | None = None
    location: str | None = None
    email: str | None = None
    notification_email: str | None = None
    hireable: bool | None = None
    bio: str | None = None
    twitter_username: str | None = None
    public_repos: int | None = None
    public_gists: int | None = None
    followers: int | None = None
    following: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    plan: GitHubUserPlan | None = None
    starred_at: str | None = None
    ldap_dn: str | None = None
    business_plus: bool | None = None


class GitHubRepositoryPermissions(_GitHubModel):
    admin: bool | None = None
    maintain: bool | None = None
    push: bool | None = None
    triage: bool | None = None
    pull: bool | None = None


class GitHubRepositoryLicense(_GitHubModel):
    key: str | None = None
    name: str | None = None
    url: str | None = None
    spdx_id: str | None = None
    node_id: str | None = None
    html_url: str | None = None


class GitHubRepository(_GitHubModel):
    id: int | None = None
    node_id: str | None = None
    name: str | None = None
    full_name: str | None = None
    owner: GitHubUser | None = None
    is_private: bool | None = Field(default=None, alias="private")
    html_url: str | None = None
    description: str | None = None
    fork: bool | None = None
    url: str | None = None
    archive_url: str | None = None
    assignees_url: str | None = None
    blobs_url: str | None = None
    branches_url: str | None = None
    collaborators_url: str | None = None
    comments_url: str | None = None
    commits_url: str | None = None
    compare_url: str | None = None
    contents_url: str | None = None
    contributors_url: str | None = None
    deployments_url: str | None = None
    downloads_url: str | None = None
    events_url: str | None = None
    forks_url: str | None = None
    git_commits_url: str | None = None
    git_refs_url: str | None = None
    git_tags_url: str | None = None
    issue_comment_url: str | None = None
    issue_events_url: str | None = None
    issues_url: str | None = None
    keys_url: str | None = None
    labels_url: str | None = None
    languages_url: str | None = None
    merges_url: str | None = None
    milestones_url: str | None = None
    notifications_url: str | None = None
    pulls_url: str | None = None
    releases_url: str | None = None
    stargazers_url: str | None = None
    statuses_url: str | None = None
    subscribers_url: str | None = None
    subscription_url: str | None = None
    tags_url: str | None = None
    teams_url: str | None = None
    trees_url: str | None = None
    hooks_url: str | None = None
    git_url: str | None = None
    ssh_url: str | None = None
    clone_url: str | None = None
    svn_url: str | None = None
    mirror_url: str | None = None
    homepage: str | None = None
    language: str | None = None
    forks_count: int | None = None
    stargazers_count: int | None = None
    watchers_count: int | None = None
    size: int | None = None
    default_branch: str | None = None
    open_issues_count: int | None = None
    forks: int | None = None
    open_issues: int | None = None
    watchers: int | None = None
    has_issues: bool | None = None
    has_projects: bool | None = None
    has_wiki: bool | None = None
    has_pages: bool | None = None
    has_discussions: bool | None = None
    has_downloads: bool | None = None
    is_template: bool | None = None
    archived: bool | None = None
    disabled: bool | None = None
    visibility: str | None = None
    pushed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    permissions: GitHubRepositoryPermissions | None = None
    allow_squash_merge: bool | None = None
    allow_merge_commit: bool | None = None
    allow_rebase_merge: bool | None = None
    allow_auto_merge: bool | None = None
    delete_branch_on_merge: bool | None = None
    allow_update_branch: bool | None = None
    squash_merge_commit_title: str | None = None
    squash_merge_commit_message: str | None = None
    merge_commit_title: str | None = None
    merge_commit_message: str | None = None
    license: GitHubRepositoryLicense | None = None
    allow_forking: bool | None = None
    web_commit_signoff_required: bool | None = None
    topics: tuple[str, ...] | None = None
    temp_clone_token: str | None = None


class GitHubGitAuthor(_GitHubModel):
    name: str | None = None
    email: str | None = None
    date: datetime | None = None


class GitHubCommitTree(_GitHubModel):
    sha: str | None = None
    url: str | None = None


class GitHubCommitVerification(_GitHubModel):
    verified: bool | None = None
    reason: str | None = None
    payload: str | None = None
    signature: str | None = None
    verified_at: str | None = None


class GitHubCommitDetail(_GitHubModel):
    url: str | None = None
    message: str | None = None
    comment_count: int | None = None
    author: GitHubGitAuthor | None = None
    committer: GitHubGitAuthor | None = None
    tree: GitHubCommitTree | None = None
    verification: GitHubCommitVerification | None = None


class GitHubCommitParent(_GitHubModel):
    sha: str | None = None
    url: str | None = None
    html_url: str | None = None


class GitHubCommitStats(_GitHubModel):
    additions: int | None = None
    deletions: int | None = None
    total: int | None = None


class GitHubDiffEntry(_GitHubModel):
    sha: str | None = None
    filename: str | None = None
    status: str | None = None
    additions: int | None = None
    deletions: int | None = None
    changes: int | None = None
    blob_url: str | None = None
    raw_url: str | None = None
    contents_url: str | None = None
    patch: str | None = None
    previous_filename: str | None = None


class GitHubCommit(_GitHubModel):
    url: str | None = None
    sha: str | None = None
    node_id: str | None = None
    html_url: str | None = None
    comments_url: str | None = None
    commit: GitHubCommitDetail | None = None
    author: GitHubUser | None = None
    committer: GitHubUser | None = None
    parents: tuple[GitHubCommitParent, ...] | None = None
    stats: GitHubCommitStats | None = None
    files: tuple[GitHubDiffEntry, ...] | None = None
