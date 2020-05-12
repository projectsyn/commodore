"""
Unit-tests for git
"""

import commodore.git as git


def test_reconstruct_api_response(tmp_path):
    repo_path = tmp_path / 'test-repo'
    repo_path.mkdir()
    repo = git.create_repository(repo_path)
    output = git.stage_all(repo)
    assert output != ""
