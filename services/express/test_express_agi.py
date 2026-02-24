#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for Express AGI Protocol implementation
"""

import unittest
from unittest.mock import patch
from io import StringIO

from express_agi import AGI


class TestAGIProtocol(unittest.TestCase):
    """Tests for AGI class - Asterisk Gateway Interface protocol"""

    def _create_agi_with_input(self, input_lines: list) -> AGI:
        """Helper to create AGI instance with mocked stdin"""
        input_data = "\n".join(input_lines) + "\n"
        with patch("sys.stdin", StringIO(input_data)):
            return AGI()

    def test_read_initial_variables(self):
        """Test parsing AGI variables at startup"""
        input_lines = [
            "agi_channel: SIP/1001-00000001",
            "agi_callerid: 0501234567",
            "agi_context: incoming",
            "agi_extension: 100",
            "",  # Empty line terminates
        ]

        agi = self._create_agi_with_input(input_lines)

        self.assertEqual(agi.variables["agi_channel"], "SIP/1001-00000001")
        self.assertEqual(agi.variables["agi_callerid"], "0501234567")
        self.assertEqual(agi.variables["agi_context"], "incoming")
        self.assertEqual(agi.variables["agi_extension"], "100")

    def test_read_initial_variables_empty_line_terminates(self):
        """Test that empty line terminates variable reading"""
        input_lines = [
            "agi_channel: SIP/1001-00000001",
            "",  # This should stop reading
            "agi_callerid: should_not_be_read",
        ]

        agi = self._create_agi_with_input(input_lines)

        self.assertIn("agi_channel", agi.variables)
        self.assertNotIn("agi_callerid", agi.variables)

    def test_read_initial_variables_with_colons_in_value(self):
        """Test parsing variables where value contains colons"""
        input_lines = ["agi_request: agi://localhost:4574/script", ""]

        agi = self._create_agi_with_input(input_lines)

        self.assertEqual(agi.variables["agi_request"], "agi://localhost:4574/script")

    @patch("sys.stdout", new_callable=StringIO)
    def test_send_command_success(self, mock_stdout):
        """Test sending command and parsing successful response"""
        agi = self._create_agi_with_input([""])

        with patch("sys.stdin", StringIO("200 result=1 (test_value)\n")):
            result = agi._send("GET VARIABLE TEST")

        self.assertEqual(mock_stdout.getvalue(), "GET VARIABLE TEST\n")
        self.assertEqual(result["code"], 200)
        self.assertEqual(result["result"], "1")
        self.assertEqual(result["data"], "(test_value)")

    @patch("sys.stdout", new_callable=StringIO)
    def test_send_command_error(self, mock_stdout):
        """Test handling error responses"""
        agi = self._create_agi_with_input([""])

        with patch("sys.stdin", StringIO("510 Invalid command\n")):
            result = agi._send("INVALID COMMAND")

        self.assertEqual(result["code"], 510)
        self.assertEqual(result["data"], "Invalid command")

    @patch("sys.stdout", new_callable=StringIO)
    def test_get_variable_found(self, mock_stdout):
        """Test getting an existing variable"""
        agi = self._create_agi_with_input([""])

        with patch("sys.stdin", StringIO("200 result=1 (my_value)\n")):
            value = agi.get_variable("MY_VAR")

        self.assertEqual(value, "my_value")
        self.assertIn("GET VARIABLE MY_VAR", mock_stdout.getvalue())

    @patch("sys.stdout", new_callable=StringIO)
    def test_get_variable_not_found(self, mock_stdout):
        """Test getting a non-existent variable returns None"""
        agi = self._create_agi_with_input([""])

        with patch("sys.stdin", StringIO("200 result=0\n")):
            value = agi.get_variable("NONEXISTENT")

        self.assertIsNone(value)

    @patch("sys.stdout", new_callable=StringIO)
    def test_set_variable(self, mock_stdout):
        """Test setting a channel variable"""
        agi = self._create_agi_with_input([""])

        with patch("sys.stdin", StringIO("200 result=1\n")):
            agi.set_variable("ULINE", "42")

        self.assertIn('SET VARIABLE ULINE "42"', mock_stdout.getvalue())

    @patch("sys.stdout", new_callable=StringIO)
    def test_verbose(self, mock_stdout):
        """Test sending verbose message"""
        agi = self._create_agi_with_input([""])

        with patch("sys.stdin", StringIO("200 result=1\n")):
            agi.verbose("Test message", 2)

        self.assertIn('VERBOSE "Test message" 2', mock_stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
