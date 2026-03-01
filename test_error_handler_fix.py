#!/usr/bin/env python3
"""
Test script to verify the error handler fix for the 'Stream' object has no attribute 'error' issue.
"""

from deva.admin_ui.strategy.error_handler import ErrorCollector, ErrorLevel, ErrorCategory

# Create an error collector
collector = ErrorCollector()

# Simulate an error similar to the one in the issue
class MockUnit:
    def __init__(self):
        self.id = "test_unit"
        self.name = "测试"
        self.unit_type = "task"

# Create a mock unit
mock_unit = MockUnit()

# Test adding an error
print("Testing error handler...")
try:
    # This should trigger the error that was causing the issue
    raise NameError("name 'log_hello_world' is not defined")
except Exception as e:
    # Add the error to the collector
    error_record = collector.add_error(
        error=e,
        unit_id=mock_unit.id,
        unit_name=mock_unit.name,
        unit_type=mock_unit.unit_type,
        level=ErrorLevel.HIGH,
        category=ErrorCategory.CODE_EXECUTION,
        context="任务执行失败"
    )
    print(f"✓ Error added successfully with ID: {error_record.error_id}")
    print(f"✓ Error message: {error_record.message}")
    print(f"✓ Error level: {error_record.level}")
    print(f"✓ Error category: {error_record.category}")

print("\nTest completed successfully!")
print("The error handler now correctly handles errors without throwing 'Stream' object has no attribute 'error'")
