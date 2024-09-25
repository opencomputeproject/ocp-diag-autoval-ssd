# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.
# pyre-unsafe
from unittest.mock import patch

from autoval.lib.test_args import TEST_CONTROL


@patch.dict(TEST_CONTROL, {})
def mock_testbase_init(self, *_):
    self.test_control = TEST_CONTROL
