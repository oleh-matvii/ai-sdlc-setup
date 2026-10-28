"""Unit tests for common.py: python3 -m unittest discover -s ~/.claude/hooks/ai-sdlc -p 'test_*.py'"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402


class IsTestPathTest(unittest.TestCase):
    def test_test_directories_and_suffixes_are_tests(self):
        for path in ("spec/models/user_spec.rb", "spec/support/helpers.rb", "test/models/user_test.rb",
                     "src/__tests__/a.js", "cypress/e2e/login.cy.ts", "e2e/flow.ts", "playwright/a.ts",
                     "src/a.test.ts", "src/a.spec.tsx", "src/a.test.mjs", "src/a.spec.cjs", "lib/x_test.rb",
                     "packages/ui/tests/button.ts"):
            with self.subTest(path=path):
                self.assertTrue(common.is_test_path(path))

    def test_code_and_lookalikes_are_not_tests(self):
        for path in ("app/models/user.rb", "app/models/spec_helper_service.rb", "src/testing.ts",
                     "src/contest.js", "lib/latest/thing.rb", "src/a.test.md", "app/models/user_spec_helper.rb"):
            with self.subTest(path=path):
                self.assertFalse(common.is_test_path(path))

    def test_docs_are_never_tests(self):
        for path in ("docs/testing/spec/a_spec.rb", "docs/superpowers/plans/test/x.md", "app/docs/tests/a.md"):
            with self.subTest(path=path):
                self.assertFalse(common.is_test_path(path))


class FindUpTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self.tmp.name)
        self.app = os.path.join(self.root, "repo", "engines", "billing")
        os.makedirs(os.path.join(self.app, "app", "models"))
        self.touch(os.path.join(self.root, "repo", "Gemfile"))
        self.file = os.path.join(self.app, "app", "models", "x.rb")
        self.touch(self.file)

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def touch(path):
        open(path, "w").close()

    def test_finds_the_nearest_ancestor_with_the_marker(self):
        self.assertEqual(common.find_up(self.file, "Gemfile"), os.path.join(self.root, "repo"))
        self.touch(os.path.join(self.app, "Gemfile"))
        self.assertEqual(common.find_up(self.file, "Gemfile"), self.app)

    def test_does_not_look_above_stop_at(self):
        self.assertIsNone(common.find_up(self.file, "Gemfile", stop_at=self.app))

    def test_marker_in_stop_at_itself_is_found(self):
        repo = os.path.join(self.root, "repo")
        self.assertEqual(common.find_up(self.file, "Gemfile", stop_at=repo), repo)

    def test_missing_marker_returns_none(self):
        self.assertIsNone(common.find_up(self.file, "package.json", stop_at=self.root))


class ChainPathsTest(unittest.TestCase):
    def test_defaults_to_the_chain_dir_keyed_by_repo_hash_and_branch(self):
        d, p = common.chain_paths("/src/app", "feat/x")
        self.assertEqual(os.path.dirname(d), common.CHAIN_DIR)
        self.assertEqual(p, os.path.join(d, "feat_x.json"))

    def test_another_base_dir_keeps_the_same_key(self):
        d, p = common.chain_paths("/src/app", "feat/x", base_dir="/state/retro")
        self.assertEqual(d, os.path.join("/state/retro", os.path.basename(common.chain_paths("/src/app", "x")[0])))
        self.assertEqual(p, os.path.join(d, "feat_x.json"))


if __name__ == "__main__":
    unittest.main()
