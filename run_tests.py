#!/usr/bin/env python3
"""
Test runner for multi-cloud FinOps tools functionality.
"""

import sys
import unittest

from tests.test_aws_tools import TestAWSTools
from tests.test_azure_tools import TestAzureTools
from tests.test_gcp_tools import TestGCPTools


def run_tests():
    """Run all cloud provider tests."""
    # Create test suite
    test_suite = unittest.TestSuite()

    # Add test cases for all cloud providers
    test_suite.addTest(unittest.makeSuite(TestAzureTools))
    test_suite.addTest(unittest.makeSuite(TestAWSTools))
    test_suite.addTest(unittest.makeSuite(TestGCPTools))

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)

    # Print summary
    print(f"\n{'='*50}")
    print("Test Summary:")
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(
        f"Success rate: {((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100):.1f}%"
    )
    print(f"{'='*50}")

    # Return exit code
    return 0 if result.wasSuccessful() else 1


def run_specific_tests(provider):
    """Run tests for a specific cloud provider."""
    providers = {"azure": TestAzureTools, "aws": TestAWSTools, "gcp": TestGCPTools}

    if provider not in providers:
        print(f"Unknown provider: {provider}")
        print("Available providers: azure, aws, gcp")
        return 1

    test_suite = unittest.TestSuite()
    test_suite.addTest(unittest.makeSuite(providers[provider]))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Run specific provider tests
        provider = sys.argv[1].lower()
        sys.exit(run_specific_tests(provider))
    else:
        # Run all tests
        sys.exit(run_tests())
