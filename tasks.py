from invoke import task
import semver
import toml
from git import Repo, GitCommandError
import os


@task
def clean(c):
    """Remove build artifacts."""
    patterns = ["build/", "dist/", "*.egg-info", "__pycache__", "*.pyc"]
    for pattern in patterns:
        c.run(f"rm -rf {pattern}")


@task
def run_tests(c):
    """Run test suite."""
    c.run("pytest")


@task
def lint(c):
    """Run code linting."""
    c.run("flake8 .")
    c.run("black . --check")


@task(pre=[clean])
def build(c):
    """Build package distributions."""
    c.run("python -m build")


@task
def update_version(c, new_version=None, part="patch"):
    """Update package version in pyproject.toml."""
    if not os.path.exists("pyproject.toml"):
        raise Exception("pyproject.toml not found")

    # Read current version
    with open("pyproject.toml", "r") as f:
        config = toml.load(f)
    current_version = config["project"]["version"]

    # Calculate new version
    if new_version is None:
        new_version = str(semver.VersionInfo.parse(current_version).bump_patch())
        if part == "minor":
            new_version = str(semver.VersionInfo.parse(current_version).bump_minor())
        elif part == "major":
            new_version = str(semver.VersionInfo.parse(current_version).bump_major())

    # Update pyproject.toml
    config["project"]["version"] = new_version
    with open("pyproject.toml", "w") as f:
        toml.dump(config, f)

    print(f"Version updated from {current_version} to {new_version}")
    return new_version


@task
def commit_version(c, version):
    """Commit version changes to git."""
    repo = Repo(".")
    repo.index.add(["pyproject.toml"])
    repo.index.commit(f"Bump version to {version}")
    print(f"Committed version bump to {version}")


@task
def create_tag(c, version):
    """Create and push a git tag for the release."""
    try:
        repo = Repo(".")
        new_tag = f"v{version}"

        # Check if tag already exists
        if new_tag in repo.tags:
            raise Exception(f"Tag {new_tag} already exists")

        # Create tag
        tag = repo.create_tag(new_tag, message=f"Release {new_tag}")

        # Push changes and tag
        origin = repo.remote("origin")
        origin.push()
        origin.push(tag)

        print(f"Created and pushed tag: {new_tag}")
    except GitCommandError as e:
        print(f"Git error: {e}")
        raise
    except Exception as e:
        print(f"Error: {e}")
        raise


@task(pre=[build])
def publish(c):
    """Publish package to PyPI."""
    c.run("python -m twine upload dist/*")


@task
def check_git_status(c):
    """Check if git working directory is clean and on main/master branch."""
    repo = Repo(".")

    # Check for uncommitted changes
    if repo.is_dirty():
        raise Exception("Working directory is not clean. Commit or stash changes first.")

    # Check current branch
    current = repo.active_branch.name
    if current not in ['main', 'master']:
        raise Exception(f"Not on main/master branch. Current branch: {current}")

    # Check for unpulled changes
    origin = repo.remote("origin")
    origin.fetch()
    commits_behind = list(repo.iter_commits(f'{current}..origin/{current}'))
    if commits_behind:
        raise Exception(f"Local branch is {len(commits_behind)} commits behind origin/{current}")

    print("Git working directory is clean and up to date.")


@task(pre=[check_git_status])
def update_and_tag(c, new_version=None, part="patch"):
    """Update version, commit, and create tag."""
    version = update_version(c, new_version, part)
    commit_version(c, version)
    create_tag(c, version)
    return version


@task(pre=[check_git_status, update_and_tag, build, publish])
def release(c, new_version=None, part="patch"):
    """Perform a full release with all checks and steps."""
    print(f"\nSuccessfully completed release process!")


@task
def show_version(c):
    """Show current version from pyproject.toml."""
    with open("pyproject.toml", "r") as f:
        config = toml.load(f)
    print(f"{config['project']['version']}")