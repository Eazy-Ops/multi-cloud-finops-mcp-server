import unittest
import subprocess
import sys

class TestCLI(unittest.TestCase):
    def test_cli_help(self):
        # Try to run the CLI with --help and check for expected output
        result = subprocess.run(
            [sys.executable, "-m", "mcp.server.fastmcp", "--help"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertTrue("help" in result.stdout.lower() or "usage" in result.stdout.lower())

if __name__ == "__main__":
    unittest.main() 