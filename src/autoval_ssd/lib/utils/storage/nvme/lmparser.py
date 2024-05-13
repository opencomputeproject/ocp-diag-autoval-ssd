#!/usr/bin/env python3

# pyre-unsafe

import argparse
import json
import re
from datetime import datetime
from typing import Dict, List, Union


class LatencyMonitorLogParser:
    """Class to parse latency monitor log files"""

    OCP2_SCHEMA = {
        "schema_level": "byte",
        "instructions": [
            {
                "field": "Latency Monitor Feature Status",
                "json_field": "Feature Status",
                "requirement_id": "LMDATA-1",
                "offset": 0,
                "size": 1,
                "json_format": "decimal",
                "subschema": {
                    "schema_level": "bit",
                    "instructions": [
                        {
                            "field": "Reserved",
                            "offset": 3,
                            "size": 5,
                            "verbose_only": True,
                        },
                        {
                            "field": "Active Measured Latency Supported",
                            "offset": 2,
                            "size": 1,
                        },
                        {
                            "field": "Active Latency Configuration/Active Latency Mode 1 Supported",
                            "offset": 1,
                            "size": 1,
                        },
                        {
                            "field": "Latency Monitoring Feature Enabled",
                            "offset": 0,
                            "size": 1,
                        },
                    ],
                },
            },
            {
                "field": "Reserved",
                "requirement_id": "LMDATA-2",
                "offset": 1,
                "size": 1,
                "verbose_only": True,
            },
            {
                "field": "Active Bucket Timer",
                "json_field": "Active Bucket Timer",
                "requirement_id": "LMDATA-3",
                "offset": 2,
                "size": 2,
                "format": "5min",
                "json_format": "decimal*5",
            },
            {
                "field": "Active Bucket Timer Threshold",
                "json_field": "Active Bucket Timer Threshold",
                "requirement_id": "LMDATA-4",
                "offset": 4,
                "size": 2,
                "format": "5min",
                "json_format": "decimal*5",
            },
            {
                "field": "Active Threshold A",
                "json_field": "Active Threshold A",
                "requirement_id": "LMDATA-5",
                "offset": 6,
                "size": 1,
                "format": "5ms+5",
                "json_format": "decimal*5+5",
            },
            {
                "field": "Active Threshold B",
                "json_field": "Active Threshold B",
                "requirement_id": "LMDATA-6",
                "offset": 7,
                "size": 1,
                "format": "5ms+5",
                "json_format": "decimal*5+5",
            },
            {
                "field": "Active Threshold C",
                "json_field": "Active Threshold C",
                "requirement_id": "LMDATA-7",
                "offset": 8,
                "size": 1,
                "format": "5ms+5",
                "json_format": "decimal*5+5",
            },
            {
                "field": "Active Threshold D",
                "json_field": "Active Threshold D",
                "requirement_id": "LMDATA-8",
                "offset": 9,
                "size": 1,
                "format": "5ms+5",
                "json_format": "decimal*5+5",
            },
            {
                "field": "Active Latency Configuration",
                "requirement_id": "LMDATA-9a",
                "offset": 10,
                "size": 2,
                "verbose_only": True,
                "subschema": {
                    "schema_level": "bit",
                    "instructions": [{"field": "Reserved", "offset": 12, "size": 4}],
                },
            },
            {
                "field": "Active Latency Configuration - Bucket 0",
                "json_field": "Active Latency Mode: Bucket 0",
                "requirement_id": "LMDATA-9b",
                "offset": 10,
                "size": 2,
                "subschema": {
                    "schema_level": "bit",
                    "instructions": [
                        {
                            "field": "Read",
                            "json_field": "Read",
                            "offset": 0,
                            "size": 1,
                            "json_format": "decimal",
                        },
                        {
                            "field": "Write",
                            "json_field": "Write",
                            "offset": 1,
                            "size": 1,
                            "json_format": "decimal",
                        },
                        {
                            "field": "Deallocate/TRIM",
                            "json_field": "Trim",
                            "offset": 2,
                            "size": 1,
                            "json_format": "decimal",
                        },
                    ],
                },
            },
            {
                "field": "Active Latency Configuration - Bucket 1",
                "json_field": "Active Latency Mode: Bucket 1",
                "requirement_id": "LMDATA-9c",
                "offset": 10,
                "size": 2,
                "subschema": {
                    "schema_level": "bit",
                    "instructions": [
                        {
                            "field": "Read",
                            "json_field": "Read",
                            "offset": 3,
                            "size": 1,
                            "json_format": "decimal",
                        },
                        {
                            "field": "Write",
                            "json_field": "Write",
                            "offset": 4,
                            "size": 1,
                            "json_format": "decimal",
                        },
                        {
                            "field": "Deallocate/TRIM",
                            "json_field": "Trim",
                            "offset": 5,
                            "size": 1,
                            "json_format": "decimal",
                        },
                    ],
                },
            },
            {
                "field": "Active Latency Configuration - Bucket 2",
                "json_field": "Active Latency Mode: Bucket 2",
                "requirement_id": "LMDATA-9d",
                "offset": 10,
                "size": 2,
                "subschema": {
                    "schema_level": "bit",
                    "instructions": [
                        {
                            "field": "Read",
                            "json_field": "Read",
                            "offset": 6,
                            "size": 1,
                            "json_format": "decimal",
                        },
                        {
                            "field": "Write",
                            "json_field": "Write",
                            "offset": 7,
                            "size": 1,
                            "json_format": "decimal",
                        },
                        {
                            "field": "Deallocate/TRIM",
                            "json_field": "Trim",
                            "offset": 8,
                            "size": 1,
                            "json_format": "decimal",
                        },
                    ],
                },
            },
            {
                "field": "Active Latency Configuration - Bucket 3",
                "json_field": "Active Latency Mode: Bucket 3",
                "requirement_id": "LMDATA-9e",
                "offset": 10,
                "size": 2,
                "subschema": {
                    "schema_level": "bit",
                    "instructions": [
                        {
                            "field": "Read",
                            "json_field": "Read",
                            "offset": 9,
                            "size": 1,
                            "json_format": "decimal",
                        },
                        {
                            "field": "Write",
                            "json_field": "Write",
                            "offset": 10,
                            "size": 1,
                            "json_format": "decimal",
                        },
                        {
                            "field": "Deallocate/TRIM",
                            "json_field": "Trim",
                            "offset": 11,
                            "size": 1,
                            "json_format": "decimal",
                        },
                    ],
                },
            },
            {
                "field": "Active Latency Minimum Window",
                "json_field": "Active Latency Minimum Window",
                "requirement_id": "LMDATA-10",
                "offset": 12,
                "size": 1,
                "format": "100ms",
                "json_format": "decimal*100",
            },
            {
                "field": "Reserved",
                "requirement_id": "LMDATA-11",
                "offset": 13,
                "size": 19,
                "verbose_only": True,
            },
            {
                "field": "Active Bucket Counter 0",
                "json_field": "Active Bucket Counter: Bucket 0",
                "requirement_id": "LMDATA-12",
                "offset": 32,
                "size": 16,
                "subschema": {
                    "schema_level": "byte",
                    "instructions": [
                        {
                            "field": "Read Command Counter",
                            "json_field": "Read",
                            "offset": 12,
                            "size": 4,
                            "format": "decimal",
                            "json_format": "decimal",
                        },
                        {
                            "field": "Write Command Counter",
                            "json_field": "Write",
                            "offset": 8,
                            "size": 4,
                            "format": "decimal",
                            "json_format": "decimal",
                        },
                        {
                            "field": "De-Allocate/TRIM Command Counter",
                            "json_field": "Trim",
                            "offset": 4,
                            "size": 4,
                            "format": "decimal",
                            "json_format": "decimal",
                        },
                        {
                            "field": "Reserved",
                            "offset": 0,
                            "size": 4,
                            "verbose_only": True,
                        },
                    ],
                },
            },
            {
                "field": "Active Bucket Counter 1",
                "json_field": "Active Bucket Counter: Bucket 1",
                "requirement_id": "LMDATA-13",
                "offset": 48,
                "size": 16,
                "subschema": {
                    "schema_level": "byte",
                    "instructions": [
                        {
                            "field": "Read Command Counter",
                            "json_field": "Read",
                            "offset": 12,
                            "size": 4,
                            "format": "decimal",
                            "json_format": "decimal",
                        },
                        {
                            "field": "Write Command Counter",
                            "json_field": "Write",
                            "offset": 8,
                            "size": 4,
                            "format": "decimal",
                            "json_format": "decimal",
                        },
                        {
                            "field": "De-Allocate/TRIM Command Counter",
                            "json_field": "Trim",
                            "offset": 4,
                            "size": 4,
                            "format": "decimal",
                            "json_format": "decimal",
                        },
                        {
                            "field": "Reserved",
                            "offset": 0,
                            "size": 4,
                            "verbose_only": True,
                        },
                    ],
                },
            },
            {
                "field": "Active Bucket Counter 2",
                "json_field": "Active Bucket Counter: Bucket 2",
                "requirement_id": "LMDATA-14",
                "offset": 64,
                "size": 16,
                "subschema": {
                    "schema_level": "byte",
                    "instructions": [
                        {
                            "field": "Read Command Counter",
                            "json_field": "Read",
                            "offset": 12,
                            "size": 4,
                            "format": "decimal",
                            "json_format": "decimal",
                        },
                        {
                            "field": "Write Command Counter",
                            "json_field": "Write",
                            "offset": 8,
                            "size": 4,
                            "format": "decimal",
                            "json_format": "decimal",
                        },
                        {
                            "field": "De-Allocate/TRIM Command Counter",
                            "json_field": "Trim",
                            "offset": 4,
                            "size": 4,
                            "format": "decimal",
                            "json_format": "decimal",
                        },
                        {
                            "field": "Reserved",
                            "offset": 0,
                            "size": 4,
                            "verbose_only": True,
                        },
                    ],
                },
            },
            {
                "field": "Active Bucket Counter 3",
                "json_field": "Active Bucket Counter: Bucket 3",
                "requirement_id": "LMDATA-15",
                "offset": 80,
                "size": 16,
                "subschema": {
                    "schema_level": "byte",
                    "instructions": [
                        {
                            "field": "Read Command Counter",
                            "json_field": "Read",
                            "offset": 12,
                            "size": 4,
                            "format": "decimal",
                            "json_format": "decimal",
                        },
                        {
                            "field": "Write Command Counter",
                            "json_field": "Write",
                            "offset": 8,
                            "size": 4,
                            "format": "decimal",
                            "json_format": "decimal",
                        },
                        {
                            "field": "De-Allocate/TRIM Command Counter",
                            "json_field": "Trim",
                            "offset": 4,
                            "size": 4,
                            "format": "decimal",
                            "json_format": "decimal",
                        },
                        {
                            "field": "Reserved",
                            "offset": 0,
                            "size": 4,
                            "verbose_only": True,
                        },
                    ],
                },
            },
            {
                "field": "Active Latency Stamp - Bucket 0",
                "json_field": "Active Latency Time Stamp: Bucket 0",
                "requirement_id": "LMDATA-16a",
                "offset": 168,
                "size": 24,
                "subschema": {
                    "schema_level": "byte",
                    "instructions": [
                        {
                            "field": "Read",
                            "json_field": "Read",
                            "offset": 16,
                            "size": 8,
                            "json_format": "timestamp",
                            "subschema": {
                                "schema_level": "bit",
                                "instructions": [
                                    {
                                        "field": "Timestamp",
                                        "offset": 0,
                                        "size": 48,
                                        "format": "timestamp",
                                    },
                                    {
                                        "field": "Timestamp Origin",
                                        "offset": 49,
                                        "size": 3,
                                    },
                                    {
                                        "field": "Synch",
                                        "offset": 48,
                                        "size": 1,
                                    },
                                    {
                                        "field": "Reserved",
                                        "offset": 52,
                                        "size": 12,
                                        "verbose_only": True,
                                    },
                                ],
                            },
                        },
                        {
                            "field": "Write",
                            "json_field": "Write",
                            "offset": 8,
                            "size": 8,
                            "json_format": "timestamp",
                            "subschema": {
                                "schema_level": "bit",
                                "instructions": [
                                    {
                                        "field": "Timestamp",
                                        "offset": 0,
                                        "size": 48,
                                        "format": "timestamp",
                                    },
                                    {
                                        "field": "Timestamp Origin",
                                        "offset": 49,
                                        "size": 3,
                                    },
                                    {
                                        "field": "Synch",
                                        "offset": 48,
                                        "size": 1,
                                    },
                                    {
                                        "field": "Reserved",
                                        "offset": 52,
                                        "size": 12,
                                        "verbose_only": True,
                                    },
                                ],
                            },
                        },
                        {
                            "field": "De-Allocate/TRIM",
                            "json_field": "Trim",
                            "offset": 0,
                            "size": 8,
                            "json_format": "timestamp",
                            "subschema": {
                                "schema_level": "bit",
                                "instructions": [
                                    {
                                        "field": "Timestamp",
                                        "offset": 0,
                                        "size": 48,
                                        "format": "timestamp",
                                    },
                                    {
                                        "field": "Timestamp Origin",
                                        "offset": 49,
                                        "size": 3,
                                    },
                                    {
                                        "field": "Synch",
                                        "offset": 48,
                                        "size": 1,
                                    },
                                    {
                                        "field": "Reserved",
                                        "offset": 52,
                                        "size": 12,
                                        "verbose_only": True,
                                    },
                                ],
                            },
                        },
                    ],
                },
            },
            {
                "field": "Active Latency Stamp - Bucket 1",
                "json_field": "Active Latency Time Stamp: Bucket 1",
                "requirement_id": "LMDATA-16b",
                "offset": 144,
                "size": 24,
                "subschema": {
                    "schema_level": "byte",
                    "instructions": [
                        {
                            "field": "Read",
                            "json_field": "Read",
                            "offset": 16,
                            "size": 8,
                            "json_format": "timestamp",
                            "subschema": {
                                "schema_level": "bit",
                                "instructions": [
                                    {
                                        "field": "Timestamp",
                                        "offset": 0,
                                        "size": 48,
                                        "format": "timestamp",
                                    },
                                    {
                                        "field": "Timestamp Origin",
                                        "offset": 49,
                                        "size": 3,
                                    },
                                    {
                                        "field": "Synch",
                                        "offset": 48,
                                        "size": 1,
                                    },
                                    {
                                        "field": "Reserved",
                                        "offset": 52,
                                        "size": 12,
                                        "verbose_only": True,
                                    },
                                ],
                            },
                        },
                        {
                            "field": "Write",
                            "json_field": "Write",
                            "offset": 8,
                            "size": 8,
                            "json_format": "timestamp",
                            "subschema": {
                                "schema_level": "bit",
                                "instructions": [
                                    {
                                        "field": "Timestamp",
                                        "offset": 0,
                                        "size": 48,
                                        "format": "timestamp",
                                    },
                                    {
                                        "field": "Timestamp Origin",
                                        "offset": 49,
                                        "size": 3,
                                    },
                                    {
                                        "field": "Synch",
                                        "offset": 48,
                                        "size": 1,
                                    },
                                    {
                                        "field": "Reserved",
                                        "offset": 52,
                                        "size": 12,
                                        "verbose_only": True,
                                    },
                                ],
                            },
                        },
                        {
                            "field": "De-Allocate/TRIM",
                            "json_field": "Trim",
                            "offset": 0,
                            "size": 8,
                            "json_format": "timestamp",
                            "subschema": {
                                "schema_level": "bit",
                                "instructions": [
                                    {
                                        "field": "Timestamp",
                                        "offset": 0,
                                        "size": 48,
                                        "format": "timestamp",
                                    },
                                    {
                                        "field": "Timestamp Origin",
                                        "offset": 49,
                                        "size": 3,
                                    },
                                    {
                                        "field": "Synch",
                                        "offset": 48,
                                        "size": 1,
                                    },
                                    {
                                        "field": "Reserved",
                                        "offset": 52,
                                        "size": 12,
                                        "verbose_only": True,
                                    },
                                ],
                            },
                        },
                    ],
                },
            },
            {
                "field": "Active Latency Stamp - Bucket 2",
                "json_field": "Active Latency Time Stamp: Bucket 2",
                "requirement_id": "LMDATA-16c",
                "offset": 120,
                "size": 24,
                "subschema": {
                    "schema_level": "byte",
                    "instructions": [
                        {
                            "field": "Read",
                            "json_field": "Read",
                            "offset": 16,
                            "size": 8,
                            "json_format": "timestamp",
                            "subschema": {
                                "schema_level": "bit",
                                "instructions": [
                                    {
                                        "field": "Timestamp",
                                        "offset": 0,
                                        "size": 48,
                                        "format": "timestamp",
                                    },
                                    {
                                        "field": "Timestamp Origin",
                                        "offset": 49,
                                        "size": 3,
                                    },
                                    {
                                        "field": "Synch",
                                        "offset": 48,
                                        "size": 1,
                                    },
                                    {
                                        "field": "Reserved",
                                        "offset": 52,
                                        "size": 12,
                                        "verbose_only": True,
                                    },
                                ],
                            },
                        },
                        {
                            "field": "Write",
                            "json_field": "Write",
                            "offset": 8,
                            "size": 8,
                            "json_format": "timestamp",
                            "subschema": {
                                "schema_level": "bit",
                                "instructions": [
                                    {
                                        "field": "Timestamp",
                                        "offset": 0,
                                        "size": 48,
                                        "format": "timestamp",
                                    },
                                    {
                                        "field": "Timestamp Origin",
                                        "offset": 49,
                                        "size": 3,
                                    },
                                    {
                                        "field": "Synch",
                                        "offset": 48,
                                        "size": 1,
                                    },
                                    {
                                        "field": "Reserved",
                                        "offset": 52,
                                        "size": 12,
                                        "verbose_only": True,
                                    },
                                ],
                            },
                        },
                        {
                            "field": "De-Allocate/TRIM",
                            "json_field": "Trim",
                            "offset": 0,
                            "size": 8,
                            "json_format": "timestamp",
                            "subschema": {
                                "schema_level": "bit",
                                "instructions": [
                                    {
                                        "field": "Timestamp",
                                        "offset": 0,
                                        "size": 48,
                                        "format": "timestamp",
                                    },
                                    {
                                        "field": "Timestamp Origin",
                                        "offset": 49,
                                        "size": 3,
                                    },
                                    {
                                        "field": "Synch",
                                        "offset": 48,
                                        "size": 1,
                                    },
                                    {
                                        "field": "Reserved",
                                        "offset": 52,
                                        "size": 12,
                                        "verbose_only": True,
                                    },
                                ],
                            },
                        },
                    ],
                },
            },
            {
                "field": "Active Latency Stamp - Bucket 3",
                "json_field": "Active Latency Time Stamp: Bucket 3",
                "requirement_id": "LMDATA-16d",
                "offset": 96,
                "size": 24,
                "subschema": {
                    "schema_level": "byte",
                    "instructions": [
                        {
                            "field": "Read",
                            "json_field": "Read",
                            "offset": 16,
                            "size": 8,
                            "json_format": "timestamp",
                            "subschema": {
                                "schema_level": "bit",
                                "instructions": [
                                    {
                                        "field": "Timestamp",
                                        "offset": 0,
                                        "size": 48,
                                        "format": "timestamp",
                                    },
                                    {
                                        "field": "Timestamp Origin",
                                        "offset": 49,
                                        "size": 3,
                                    },
                                    {
                                        "field": "Synch",
                                        "offset": 48,
                                        "size": 1,
                                    },
                                    {
                                        "field": "Reserved",
                                        "offset": 52,
                                        "size": 12,
                                        "verbose_only": True,
                                    },
                                ],
                            },
                        },
                        {
                            "field": "Write",
                            "json_field": "Write",
                            "offset": 8,
                            "size": 8,
                            "json_format": "timestamp",
                            "subschema": {
                                "schema_level": "bit",
                                "instructions": [
                                    {
                                        "field": "Timestamp",
                                        "offset": 0,
                                        "size": 48,
                                        "format": "timestamp",
                                    },
                                    {
                                        "field": "Timestamp Origin",
                                        "offset": 49,
                                        "size": 3,
                                    },
                                    {
                                        "field": "Synch",
                                        "offset": 48,
                                        "size": 1,
                                    },
                                    {
                                        "field": "Reserved",
                                        "offset": 52,
                                        "size": 12,
                                        "verbose_only": True,
                                    },
                                ],
                            },
                        },
                        {
                            "field": "De-Allocate/TRIM",
                            "json_field": "Trim",
                            "offset": 0,
                            "size": 8,
                            "json_format": "timestamp",
                            "subschema": {
                                "schema_level": "bit",
                                "instructions": [
                                    {
                                        "field": "Timestamp",
                                        "offset": 0,
                                        "size": 48,
                                        "format": "timestamp",
                                    },
                                    {
                                        "field": "Timestamp Origin",
                                        "offset": 49,
                                        "size": 3,
                                    },
                                    {
                                        "field": "Synch",
                                        "offset": 48,
                                        "size": 1,
                                    },
                                    {
                                        "field": "Reserved",
                                        "offset": 52,
                                        "size": 12,
                                        "verbose_only": True,
                                    },
                                ],
                            },
                        },
                    ],
                },
            },
            {
                "field": "Active Measured Latency - Bucket 0",
                "json_field": "Active Measured Latency: Bucket 0",
                "requirement_id": "LMDATA-17a",
                "offset": 210,
                "size": 6,
                "subschema": {
                    "schema_level": "byte",
                    "instructions": [
                        {
                            "field": "Read",
                            "json_field": "Read",
                            "offset": 4,
                            "size": 2,
                            "format": "1ms",
                            "json_format": "decimal",
                        },
                        {
                            "field": "Write",
                            "json_field": "Write",
                            "offset": 2,
                            "size": 2,
                            "format": "1ms",
                            "json_format": "decimal",
                        },
                        {
                            "field": "De-Allocate/TRIM",
                            "json_field": "Trim",
                            "offset": 0,
                            "size": 2,
                            "format": "1ms",
                            "json_format": "decimal",
                        },
                    ],
                },
            },
            {
                "field": "Active Measured Latency - Bucket 1",
                "json_field": "Active Measured Latency: Bucket 1",
                "requirement_id": "LMDATA-17b",
                "offset": 204,
                "size": 6,
                "subschema": {
                    "schema_level": "byte",
                    "instructions": [
                        {
                            "field": "Read",
                            "json_field": "Read",
                            "offset": 4,
                            "size": 2,
                            "format": "1ms",
                            "json_format": "decimal",
                        },
                        {
                            "field": "Write",
                            "json_field": "Write",
                            "offset": 2,
                            "size": 2,
                            "format": "1ms",
                            "json_format": "decimal",
                        },
                        {
                            "field": "De-Allocate/TRIM",
                            "json_field": "Trim",
                            "offset": 0,
                            "size": 2,
                            "format": "1ms",
                            "json_format": "decimal",
                        },
                    ],
                },
            },
            {
                "field": "Active Measured Latency - Bucket 2",
                "json_field": "Active Measured Latency: Bucket 2",
                "requirement_id": "LMDATA-17c",
                "offset": 198,
                "size": 6,
                "subschema": {
                    "schema_level": "byte",
                    "instructions": [
                        {
                            "field": "Read",
                            "json_field": "Read",
                            "offset": 4,
                            "size": 2,
                            "format": "1ms",
                            "json_format": "decimal",
                        },
                        {
                            "field": "Write",
                            "json_field": "Write",
                            "offset": 2,
                            "size": 2,
                            "format": "1ms",
                            "json_format": "decimal",
                        },
                        {
                            "field": "De-Allocate/TRIM",
                            "json_field": "Trim",
                            "offset": 0,
                            "size": 2,
                            "format": "1ms",
                            "json_format": "decimal",
                        },
                    ],
                },
            },
            {
                "field": "Active Measured Latency - Bucket 3",
                "json_field": "Active Measured Latency: Bucket 3",
                "requirement_id": "LMDATA-17d",
                "offset": 192,
                "size": 6,
                "subschema": {
                    "schema_level": "byte",
                    "instructions": [
                        {
                            "field": "Read",
                            "json_field": "Read",
                            "offset": 4,
                            "size": 2,
                            "format": "1ms",
                            "json_format": "decimal",
                        },
                        {
                            "field": "Write",
                            "json_field": "Write",
                            "offset": 2,
                            "size": 2,
                            "format": "1ms",
                            "json_format": "decimal",
                        },
                        {
                            "field": "De-Allocate/TRIM",
                            "json_field": "Trim",
                            "offset": 0,
                            "size": 2,
                            "format": "1ms",
                            "json_format": "decimal",
                        },
                    ],
                },
            },
            {
                "field": "Active Latency Stamp Units",
                "json_field": "Active Latency Stamp Units",
                "requirement_id": "LMDATA-18",
                "offset": 216,
                "size": 2,
                "json_format": "decimal",
                "subschema": {
                    "schema_level": "bit",
                    "instructions": [
                        {
                            "field": "Reserved",
                            "offset": 12,
                            "size": 4,
                            "verbose_only": True,
                        },
                        {"field": "Bucket 0 Read", "offset": 0, "size": 1},
                        {"field": "Bucket 0 Write", "offset": 1, "size": 1},
                        {"field": "Bucket 0 Deallocate/TRIM", "offset": 2, "size": 1},
                        {"field": "Bucket 1 Read", "offset": 3, "size": 1},
                        {"field": "Bucket 1 Write", "offset": 4, "size": 1},
                        {"field": "Bucket 1 Deallocate/TRIM", "offset": 5, "size": 1},
                        {"field": "Bucket 2 Read", "offset": 6, "size": 1},
                        {"field": "Bucket 2 Write", "offset": 7, "size": 1},
                        {"field": "Bucket 2 Deallocate/TRIM", "offset": 8, "size": 1},
                        {"field": "Bucket 3 Read", "offset": 9, "size": 1},
                        {"field": "Bucket 3 Write", "offset": 10, "size": 1},
                        {"field": "Bucket 3 Deallocate/TRIM", "offset": 11, "size": 1},
                    ],
                },
            },
            {
                "field": "Reserved",
                "requirement_id": "LMDATA-19",
                "offset": 218,
                "size": 22,
                "verbose_only": True,
            },
            {
                "field": "Static Bucket Counter 0",
                "json_field": "Static Bucket Counter: Bucket 0",
                "requirement_id": "LMDATA-20",
                "offset": 240,
                "size": 16,
                "subschema": {
                    "schema_level": "byte",
                    "instructions": [
                        {
                            "field": "Read Command Counter",
                            "json_field": "Read",
                            "offset": 12,
                            "size": 4,
                            "format": "decimal",
                            "json_format": "decimal",
                        },
                        {
                            "field": "Write Command Counter",
                            "json_field": "Write",
                            "offset": 8,
                            "size": 4,
                            "format": "decimal",
                            "json_format": "decimal",
                        },
                        {
                            "field": "De-Allocate/TRIM Command Counter",
                            "json_field": "Trim",
                            "offset": 4,
                            "size": 4,
                            "format": "decimal",
                            "json_format": "decimal",
                        },
                        {
                            "field": "Reserved",
                            "offset": 0,
                            "size": 4,
                            "verbose_only": True,
                        },
                    ],
                },
            },
            {
                "field": "Static Bucket Counter 1",
                "json_field": "Static Bucket Counter: Bucket 1",
                "requirement_id": "LMDATA-21",
                "offset": 256,
                "size": 16,
                "subschema": {
                    "schema_level": "byte",
                    "instructions": [
                        {
                            "field": "Read Command Counter",
                            "json_field": "Read",
                            "offset": 12,
                            "size": 4,
                            "format": "decimal",
                            "json_format": "decimal",
                        },
                        {
                            "field": "Write Command Counter",
                            "json_field": "Write",
                            "offset": 8,
                            "size": 4,
                            "format": "decimal",
                            "json_format": "decimal",
                        },
                        {
                            "field": "De-Allocate/TRIM Command Counter",
                            "json_field": "Trim",
                            "offset": 4,
                            "size": 4,
                            "format": "decimal",
                            "json_format": "decimal",
                        },
                        {
                            "field": "Reserved",
                            "offset": 0,
                            "size": 4,
                            "verbose_only": True,
                        },
                    ],
                },
            },
            {
                "field": "Static Bucket Counter 2",
                "json_field": "Static Bucket Counter: Bucket 2",
                "requirement_id": "LMDATA-22",
                "offset": 272,
                "size": 16,
                "subschema": {
                    "schema_level": "byte",
                    "instructions": [
                        {
                            "field": "Read Command Counter",
                            "json_field": "Read",
                            "offset": 12,
                            "size": 4,
                            "format": "decimal",
                            "json_format": "decimal",
                        },
                        {
                            "field": "Write Command Counter",
                            "json_field": "Write",
                            "offset": 8,
                            "size": 4,
                            "format": "decimal",
                            "json_format": "decimal",
                        },
                        {
                            "field": "De-Allocate/TRIM Command Counter",
                            "json_field": "Trim",
                            "offset": 4,
                            "size": 4,
                            "format": "decimal",
                            "json_format": "decimal",
                        },
                        {
                            "field": "Reserved",
                            "offset": 0,
                            "size": 4,
                            "verbose_only": True,
                        },
                    ],
                },
            },
            {
                "field": "Static Bucket Counter 3",
                "json_field": "Static Bucket Counter: Bucket 3",
                "requirement_id": "LMDATA-23",
                "offset": 288,
                "size": 16,
                "subschema": {
                    "schema_level": "byte",
                    "instructions": [
                        {
                            "field": "Read Command Counter",
                            "json_field": "Read",
                            "offset": 12,
                            "size": 4,
                            "format": "decimal",
                            "json_format": "decimal",
                        },
                        {
                            "field": "Write Command Counter",
                            "json_field": "Write",
                            "offset": 8,
                            "size": 4,
                            "format": "decimal",
                            "json_format": "decimal",
                        },
                        {
                            "field": "De-Allocate/TRIM Command Counter",
                            "json_field": "Trim",
                            "offset": 4,
                            "size": 4,
                            "format": "decimal",
                            "json_format": "decimal",
                        },
                        {
                            "field": "Reserved",
                            "offset": 0,
                            "size": 4,
                            "verbose_only": True,
                        },
                    ],
                },
            },
            {
                "field": "Static Latency Stamp - Bucket 0",
                "json_field": "Static Latency Time Stamp: Bucket 0",
                "requirement_id": "LMDATA-24a",
                "offset": 376,
                "size": 24,
                "subschema": {
                    "schema_level": "byte",
                    "instructions": [
                        {
                            "field": "Read",
                            "json_field": "Read",
                            "offset": 16,
                            "size": 8,
                            "json_format": "timestamp",
                            "subschema": {
                                "schema_level": "bit",
                                "instructions": [
                                    {
                                        "field": "Timestamp",
                                        "offset": 0,
                                        "size": 48,
                                        "format": "timestamp",
                                    },
                                    {
                                        "field": "Timestamp Origin",
                                        "offset": 49,
                                        "size": 3,
                                    },
                                    {
                                        "field": "Synch",
                                        "offset": 48,
                                        "size": 1,
                                    },
                                    {
                                        "field": "Reserved",
                                        "offset": 52,
                                        "size": 12,
                                        "verbose_only": True,
                                    },
                                ],
                            },
                        },
                        {
                            "field": "Write",
                            "json_field": "Write",
                            "offset": 8,
                            "size": 8,
                            "json_format": "timestamp",
                            "subschema": {
                                "schema_level": "bit",
                                "instructions": [
                                    {
                                        "field": "Timestamp",
                                        "offset": 0,
                                        "size": 48,
                                        "format": "timestamp",
                                    },
                                    {
                                        "field": "Timestamp Origin",
                                        "offset": 49,
                                        "size": 3,
                                    },
                                    {
                                        "field": "Synch",
                                        "offset": 48,
                                        "size": 1,
                                    },
                                    {
                                        "field": "Reserved",
                                        "offset": 52,
                                        "size": 12,
                                        "verbose_only": True,
                                    },
                                ],
                            },
                        },
                        {
                            "field": "De-Allocate/TRIM",
                            "json_field": "Trim",
                            "offset": 0,
                            "size": 8,
                            "json_format": "timestamp",
                            "subschema": {
                                "schema_level": "bit",
                                "instructions": [
                                    {
                                        "field": "Timestamp",
                                        "offset": 0,
                                        "size": 48,
                                        "format": "timestamp",
                                    },
                                    {
                                        "field": "Timestamp Origin",
                                        "offset": 49,
                                        "size": 3,
                                    },
                                    {
                                        "field": "Synch",
                                        "offset": 48,
                                        "size": 1,
                                    },
                                    {
                                        "field": "Reserved",
                                        "offset": 52,
                                        "size": 12,
                                        "verbose_only": True,
                                    },
                                ],
                            },
                        },
                    ],
                },
            },
            {
                "field": "Static Latency Stamp - Bucket 1",
                "json_field": "Static Latency Time Stamp: Bucket 1",
                "requirement_id": "LMDATA-24b",
                "offset": 352,
                "size": 24,
                "subschema": {
                    "schema_level": "byte",
                    "instructions": [
                        {
                            "field": "Read",
                            "json_field": "Read",
                            "offset": 16,
                            "size": 8,
                            "json_format": "timestamp",
                            "subschema": {
                                "schema_level": "bit",
                                "instructions": [
                                    {
                                        "field": "Timestamp",
                                        "offset": 0,
                                        "size": 48,
                                        "format": "timestamp",
                                    },
                                    {
                                        "field": "Timestamp Origin",
                                        "offset": 49,
                                        "size": 3,
                                    },
                                    {
                                        "field": "Synch",
                                        "offset": 48,
                                        "size": 1,
                                    },
                                    {
                                        "field": "Reserved",
                                        "offset": 52,
                                        "size": 12,
                                        "verbose_only": True,
                                    },
                                ],
                            },
                        },
                        {
                            "field": "Write",
                            "json_field": "Write",
                            "offset": 8,
                            "size": 8,
                            "json_format": "timestamp",
                            "subschema": {
                                "schema_level": "bit",
                                "instructions": [
                                    {
                                        "field": "Timestamp",
                                        "offset": 0,
                                        "size": 48,
                                        "format": "timestamp",
                                    },
                                    {
                                        "field": "Timestamp Origin",
                                        "offset": 49,
                                        "size": 3,
                                    },
                                    {
                                        "field": "Synch",
                                        "offset": 48,
                                        "size": 1,
                                    },
                                    {
                                        "field": "Reserved",
                                        "offset": 52,
                                        "size": 12,
                                        "verbose_only": True,
                                    },
                                ],
                            },
                        },
                        {
                            "field": "De-Allocate/TRIM",
                            "json_field": "Trim",
                            "offset": 0,
                            "size": 8,
                            "json_format": "timestamp",
                            "subschema": {
                                "schema_level": "bit",
                                "instructions": [
                                    {
                                        "field": "Timestamp",
                                        "offset": 0,
                                        "size": 48,
                                        "format": "timestamp",
                                    },
                                    {
                                        "field": "Timestamp Origin",
                                        "offset": 49,
                                        "size": 3,
                                    },
                                    {
                                        "field": "Synch",
                                        "offset": 48,
                                        "size": 1,
                                    },
                                    {
                                        "field": "Reserved",
                                        "offset": 52,
                                        "size": 12,
                                        "verbose_only": True,
                                    },
                                ],
                            },
                        },
                    ],
                },
            },
            {
                "field": "Static Latency Stamp - Bucket 2",
                "json_field": "Static Latency Time Stamp: Bucket 2",
                "requirement_id": "LMDATA-24c",
                "offset": 328,
                "size": 24,
                "subschema": {
                    "schema_level": "byte",
                    "instructions": [
                        {
                            "field": "Read",
                            "json_field": "Read",
                            "offset": 16,
                            "size": 8,
                            "json_format": "timestamp",
                            "subschema": {
                                "schema_level": "bit",
                                "instructions": [
                                    {
                                        "field": "Timestamp",
                                        "offset": 0,
                                        "size": 48,
                                        "format": "timestamp",
                                    },
                                    {
                                        "field": "Timestamp Origin",
                                        "offset": 49,
                                        "size": 3,
                                    },
                                    {
                                        "field": "Synch",
                                        "offset": 48,
                                        "size": 1,
                                    },
                                    {
                                        "field": "Reserved",
                                        "offset": 52,
                                        "size": 12,
                                        "verbose_only": True,
                                    },
                                ],
                            },
                        },
                        {
                            "field": "Write",
                            "json_field": "Write",
                            "offset": 8,
                            "size": 8,
                            "json_format": "timestamp",
                            "subschema": {
                                "schema_level": "bit",
                                "instructions": [
                                    {
                                        "field": "Timestamp",
                                        "offset": 0,
                                        "size": 48,
                                        "format": "timestamp",
                                    },
                                    {
                                        "field": "Timestamp Origin",
                                        "offset": 49,
                                        "size": 3,
                                    },
                                    {
                                        "field": "Synch",
                                        "offset": 48,
                                        "size": 1,
                                    },
                                    {
                                        "field": "Reserved",
                                        "offset": 52,
                                        "size": 12,
                                        "verbose_only": True,
                                    },
                                ],
                            },
                        },
                        {
                            "field": "De-Allocate/TRIM",
                            "json_field": "Trim",
                            "offset": 0,
                            "size": 8,
                            "json_format": "timestamp",
                            "subschema": {
                                "schema_level": "bit",
                                "instructions": [
                                    {
                                        "field": "Timestamp",
                                        "offset": 0,
                                        "size": 48,
                                        "format": "timestamp",
                                    },
                                    {
                                        "field": "Timestamp Origin",
                                        "offset": 49,
                                        "size": 3,
                                    },
                                    {
                                        "field": "Synch",
                                        "offset": 48,
                                        "size": 1,
                                    },
                                    {
                                        "field": "Reserved",
                                        "offset": 52,
                                        "size": 12,
                                        "verbose_only": True,
                                    },
                                ],
                            },
                        },
                    ],
                },
            },
            {
                "field": "Static Latency Stamp - Bucket 3",
                "json_field": "Static Latency Time Stamp: Bucket 3",
                "requirement_id": "LMDATA-24d",
                "offset": 304,
                "size": 24,
                "subschema": {
                    "schema_level": "byte",
                    "instructions": [
                        {
                            "field": "Read",
                            "json_field": "Read",
                            "offset": 16,
                            "size": 8,
                            "json_format": "timestamp",
                            "subschema": {
                                "schema_level": "bit",
                                "instructions": [
                                    {
                                        "field": "Timestamp",
                                        "offset": 0,
                                        "size": 48,
                                        "format": "timestamp",
                                    },
                                    {
                                        "field": "Timestamp Origin",
                                        "offset": 49,
                                        "size": 3,
                                    },
                                    {
                                        "field": "Synch",
                                        "offset": 48,
                                        "size": 1,
                                    },
                                    {
                                        "field": "Reserved",
                                        "offset": 52,
                                        "size": 12,
                                        "verbose_only": True,
                                    },
                                ],
                            },
                        },
                        {
                            "field": "Write",
                            "json_field": "Write",
                            "offset": 8,
                            "size": 8,
                            "json_format": "timestamp",
                            "subschema": {
                                "schema_level": "bit",
                                "instructions": [
                                    {
                                        "field": "Timestamp",
                                        "offset": 0,
                                        "size": 48,
                                        "format": "timestamp",
                                    },
                                    {
                                        "field": "Timestamp Origin",
                                        "offset": 49,
                                        "size": 3,
                                    },
                                    {
                                        "field": "Synch",
                                        "offset": 48,
                                        "size": 1,
                                    },
                                    {
                                        "field": "Reserved",
                                        "offset": 52,
                                        "size": 12,
                                        "verbose_only": True,
                                    },
                                ],
                            },
                        },
                        {
                            "field": "De-Allocate/TRIM",
                            "json_field": "Trim",
                            "offset": 0,
                            "size": 8,
                            "json_format": "timestamp",
                            "subschema": {
                                "schema_level": "bit",
                                "instructions": [
                                    {
                                        "field": "Timestamp",
                                        "offset": 0,
                                        "size": 48,
                                        "format": "timestamp",
                                    },
                                    {
                                        "field": "Timestamp Origin",
                                        "offset": 49,
                                        "size": 3,
                                    },
                                    {
                                        "field": "Synch",
                                        "offset": 48,
                                        "size": 1,
                                    },
                                    {
                                        "field": "Reserved",
                                        "offset": 52,
                                        "size": 12,
                                        "verbose_only": True,
                                    },
                                ],
                            },
                        },
                    ],
                },
            },
            {
                "field": "Static Measured Latency - Bucket 0",
                "json_field": "Static Measured Latency: Bucket 0",
                "requirement_id": "LMDATA-25a",
                "offset": 418,
                "size": 6,
                "subschema": {
                    "schema_level": "byte",
                    "instructions": [
                        {
                            "field": "Read",
                            "json_field": "Read",
                            "offset": 4,
                            "size": 2,
                            "format": "1ms",
                            "json_format": "decimal",
                        },
                        {
                            "field": "Write",
                            "json_field": "Write",
                            "offset": 2,
                            "size": 2,
                            "format": "1ms",
                            "json_format": "decimal",
                        },
                        {
                            "field": "De-Allocate/TRIM",
                            "json_field": "Trim",
                            "offset": 0,
                            "size": 2,
                            "format": "1ms",
                            "json_format": "decimal",
                        },
                    ],
                },
            },
            {
                "field": "Static Measured Latency - Bucket 1",
                "json_field": "Static Measured Latency: Bucket 1",
                "requirement_id": "LMDATA-25b",
                "offset": 412,
                "size": 6,
                "subschema": {
                    "schema_level": "byte",
                    "instructions": [
                        {
                            "field": "Read",
                            "json_field": "Read",
                            "offset": 4,
                            "size": 2,
                            "format": "1ms",
                            "json_format": "decimal",
                        },
                        {
                            "field": "Write",
                            "json_field": "Write",
                            "offset": 2,
                            "size": 2,
                            "format": "1ms",
                            "json_format": "decimal",
                        },
                        {
                            "field": "De-Allocate/TRIM",
                            "json_field": "Trim",
                            "offset": 0,
                            "size": 2,
                            "format": "1ms",
                            "json_format": "decimal",
                        },
                    ],
                },
            },
            {
                "field": "Static Measured Latency - Bucket 2",
                "json_field": "Static Measured Latency: Bucket 2",
                "requirement_id": "LMDATA-25c",
                "offset": 406,
                "size": 6,
                "subschema": {
                    "schema_level": "byte",
                    "instructions": [
                        {
                            "field": "Read",
                            "json_field": "Read",
                            "offset": 4,
                            "size": 2,
                            "format": "1ms",
                            "json_format": "decimal",
                        },
                        {
                            "field": "Write",
                            "json_field": "Write",
                            "offset": 2,
                            "size": 2,
                            "format": "1ms",
                            "json_format": "decimal",
                        },
                        {
                            "field": "De-Allocate/TRIM",
                            "json_field": "Trim",
                            "offset": 0,
                            "size": 2,
                            "format": "1ms",
                            "json_format": "decimal",
                        },
                    ],
                },
            },
            {
                "field": "Static Measured Latency - Bucket 3",
                "json_field": "Static Measured Latency: Bucket 3",
                "requirement_id": "LMDATA-25d",
                "offset": 400,
                "size": 6,
                "subschema": {
                    "schema_level": "byte",
                    "instructions": [
                        {
                            "field": "Read",
                            "json_field": "Read",
                            "offset": 4,
                            "size": 2,
                            "format": "1ms",
                            "json_format": "decimal",
                        },
                        {
                            "field": "Write",
                            "json_field": "Write",
                            "offset": 2,
                            "size": 2,
                            "format": "1ms",
                            "json_format": "decimal",
                        },
                        {
                            "field": "De-Allocate/TRIM",
                            "json_field": "Trim",
                            "offset": 0,
                            "size": 2,
                            "format": "1ms",
                            "json_format": "decimal",
                        },
                    ],
                },
            },
            {
                "field": "Static Latency Stamp Units",
                "json_field": "Static Latency Stamp Units",
                "requirement_id": "LMDATA-26",
                "offset": 424,
                "size": 2,
                "json_format": "decimal",
                "subschema": {
                    "schema_level": "bit",
                    "instructions": [
                        {
                            "field": "Reserved",
                            "offset": 12,
                            "size": 4,
                            "verbose_only": True,
                        },
                        {"field": "Bucket 0 Read", "offset": 0, "size": 1},
                        {"field": "Bucket 0 Write", "offset": 1, "size": 1},
                        {"field": "Bucket 0 Deallocate/TRIM", "offset": 2, "size": 1},
                        {"field": "Bucket 1 Read", "offset": 3, "size": 1},
                        {"field": "Bucket 1 Write", "offset": 4, "size": 1},
                        {"field": "Bucket 1 Deallocate/TRIM", "offset": 5, "size": 1},
                        {
                            "field": "Bucket 2 Read",
                            "offset": 6,
                            "size": 1,
                            "format": "decimal",
                        },
                        {"field": "Bucket 2 Write", "offset": 7, "size": 1},
                        {"field": "Bucket 2 Deallocate/TRIM", "offset": 8, "size": 1},
                        {"field": "Bucket 3 Read", "offset": 9, "size": 1},
                        {"field": "Bucket 3 Write", "offset": 10, "size": 1},
                        {"field": "Bucket 3 Deallocate/TRIM", "offset": 11, "size": 1},
                    ],
                },
            },
            {
                "field": "Reserved",
                "requirement_id": "LMDATA-27",
                "offset": 426,
                "size": 22,
                "verbose_only": True,
            },
            {
                "field": "Debug Log Trigger Enable",
                "json_field": "Debug Log Trigger Enable",
                "requirement_id": "LMDATA-28",
                "offset": 448,
                "size": 2,
                "json_format": "decimal",
                "subschema": {
                    "schema_level": "bit",
                    "instructions": [
                        {
                            "field": "Reserved",
                            "offset": 12,
                            "size": 4,
                            "verbose_only": True,
                        },
                        {"field": "Bucket 0 Read", "offset": 0, "size": 1},
                        {"field": "Bucket 0 Write", "offset": 1, "size": 1},
                        {"field": "Bucket 0 Deallocate/TRIM", "offset": 2, "size": 1},
                        {"field": "Bucket 1 Read", "offset": 3, "size": 1},
                        {"field": "Bucket 1 Write", "offset": 4, "size": 1},
                        {"field": "Bucket 1 Deallocate/TRIM", "offset": 5, "size": 1},
                        {"field": "Bucket 2 Read", "offset": 6, "size": 1},
                        {"field": "Bucket 2 Write", "offset": 7, "size": 1},
                        {"field": "Bucket 2 Deallocate/TRIM", "offset": 8, "size": 1},
                        {"field": "Bucket 3 Read", "offset": 9, "size": 1},
                        {"field": "Bucket 3 Write", "offset": 10, "size": 1},
                        {"field": "Bucket 3 Deallocate/TRIM", "offset": 11, "size": 1},
                    ],
                },
            },
            {
                "field": "Debug Log Measured Latency",
                "json_field": "Debug Log Measured Latency",
                "requirement_id": "LMDATA-29",
                "offset": 450,
                "size": 2,
                "format": "1ms",
                "json_format": "decimal",
            },
            {
                "field": "Debug Log Latency Stamp",
                "json_field": "Debug Log Latency Time Stamp",
                "requirement_id": "LMDATA-30",
                "offset": 452,
                "size": 8,
                "json_format": "timestamp",
                "subschema": {
                    "schema_level": "bit",
                    "instructions": [
                        {
                            "field": "Timestamp",
                            "offset": 0,
                            "size": 48,
                            "format": "timestamp",
                        },
                        {
                            "field": "Timestamp Origin",
                            "offset": 49,
                            "size": 3,
                        },
                        {
                            "field": "Synch",
                            "offset": 48,
                            "size": 1,
                        },
                        {
                            "field": "Reserved",
                            "offset": 52,
                            "size": 12,
                            "verbose_only": True,
                        },
                    ],
                },
            },
            {
                "field": "Debug Log Pointer",
                "json_field": "Debug Log Pointer",
                "requirement_id": "LMDATA-31",
                "offset": 460,
                "size": 2,
            },
            {
                "field": "Debug Counter Trigger Source",
                "json_field": "Debug Counter Trigger Source",
                "requirement_id": "LMDATA-32",
                "offset": 462,
                "size": 2,
                "json_format": "decimal",
                "subschema": {
                    "schema_level": "bit",
                    "instructions": [
                        {
                            "field": "Reserved",
                            "offset": 12,
                            "size": 4,
                            "verbose_only": True,
                        },
                        {"field": "Bucket 0 Read", "offset": 0, "size": 1},
                        {"field": "Bucket 0 Write", "offset": 1, "size": 1},
                        {"field": "Bucket 0 Deallocate/TRIM", "offset": 2, "size": 1},
                        {"field": "Bucket 1 Read", "offset": 3, "size": 1},
                        {"field": "Bucket 1 Write", "offset": 4, "size": 1},
                        {"field": "Bucket 1 Deallocate/TRIM", "offset": 5, "size": 1},
                        {"field": "Bucket 2 Read", "offset": 6, "size": 1},
                        {"field": "Bucket 2 Write", "offset": 7, "size": 1},
                        {"field": "Bucket 2 Deallocate/TRIM", "offset": 8, "size": 1},
                        {"field": "Bucket 3 Read", "offset": 9, "size": 1},
                        {"field": "Bucket 3 Write", "offset": 10, "size": 1},
                        {"field": "Bucket 3 Deallocate/TRIM", "offset": 11, "size": 1},
                    ],
                },
            },
            {
                "field": "Debug Log Stamp Units",
                "json_field": "Debug Log Stamp Units",
                "requirement_id": "LMDATA-33",
                "offset": 464,
                "size": 1,
                "json_format": "decimal",
                "subschema": {
                    "schema_level": "bit",
                    "instructions": [
                        {
                            "field": "Reserved",
                            "offset": 1,
                            "size": 7,
                            "verbose_only": True,
                        },
                        {"field": "Debug Latency Stamp Basis", "offset": 0, "size": 1},
                    ],
                },
            },
            {
                "field": "Reserved",
                "requirement_id": "LMDATA-34",
                "offset": 465,
                "size": 29,
                "verbose_only": True,
            },
            {
                "field": "Log Page Version",
                "json_field": "Log Page Version",
                "requirement_id": "LMDATA-35",
                "offset": 494,
                "size": 2,
                "format": "uppercase",
                "json_format": "decimal",
            },
            {
                "field": "Log Page GUID",
                "json_field": "Log Page GUID",
                "requirement_id": "LMDATA-36",
                "offset": 496,
                "size": 16,
                "format": "uppercase",
                "json_format": "uppercase",
            },
        ],
    }

    def bytelist_to_bytestring(
        self, bytelist: List[str], little_endian: bool = True
    ) -> str:
        """
        Converts a list of bytes into a string with respect to endian format
        Eg: ['07','d7','a2'] in little endian returns "a2d707"
            ['07','d7','a2'] in big endian returns "07d7a2"
        """
        output = ""
        if little_endian:
            bytelist = list(reversed(bytelist))
        for byte in bytelist:
            output += byte
        return output

    def datastring_to_decimal(self, data: str, data_type: str) -> int:
        """
        Converts a binary or hexadecimal string into an integer
        Eg: "a2d707" in hexadecimal returns 10671879
            "0111" in binary returns 7
        """
        if data_type == "binary":
            return int(data, 2)
        if data_type == "hexadecimal":
            return int(data, 16)
        raise ValueError("Unrecognized data type for datastring to decimal conversion!")

    def format_timestamp_output(self, data: str, data_type: str) -> str:
        """Formats timestamp based on timestamp data structure for get features as specified in NVM Express Revision 1.4"""
        if data_type == "binary":
            if data == "1" * 48:
                return "NA"
            milliseconds = int(data, 2)
            datetimestring = datetime.utcfromtimestamp(milliseconds / 1000).isoformat(
                sep=" ", timespec="milliseconds"
            )
            return f"{datetimestring} GMT"
        if data_type == "hexadecimal":
            if data == "f" * 16:
                return "NA"
            binarydata = bin(int(data, 16))[2:].zfill(len(data) * 4)
            timestamp = binarydata[16:64]
            milliseconds = int(timestamp, 2)
            datetimestring = datetime.utcfromtimestamp(milliseconds / 1000).isoformat(
                sep=" ", timespec="milliseconds"
            )
            return f"{datetimestring} GMT"
        raise ValueError("Unrecognized data type for timestamp formatting!")

    def format_humanreadable_output_prefix(self, depth: int) -> str:
        """
        Formats and returns output line prefix for field based on its depth in the schema
        Eg: returns "" for depth 0, which is the outermost schema
            returns "\t- " for depth 1, which is the first level of nesting/subschema
            returns "\t\t-- " for depth 2, and so on
        """
        output = "\t" * depth
        if depth > 0:
            output += "-" * depth
            output += " "
        return output

    def format_humanreadable_instruction_output(
        self, field: str, data: str, data_type: str, format_type: str
    ) -> str:
        """Formats and returns output line for field based on the specified formatting"""
        if format_type == "5min":
            int_data = self.datastring_to_decimal(data, data_type) * 5
            return f"{field}: {int_data} min\n"
        if format_type == "5ms+5":
            int_data = self.datastring_to_decimal(data, data_type) * 5 + 5
            return f"{field}: {int_data} ms\n"
        if format_type == "100ms":
            int_data = self.datastring_to_decimal(data, data_type) * 100
            return f"{field}: {int_data} ms\n"
        if format_type == "1ms":
            int_data = self.datastring_to_decimal(data, data_type)
            return f"{field}: {int_data} ms\n"
        if format_type == "decimal":
            int_data = self.datastring_to_decimal(data, data_type)
            return f"{field}: {int_data}\n"
        if format_type == "uppercase":
            return f"{field}: {data.upper()}\n"
        if format_type == "timestamp":
            data = self.format_timestamp_output(data, data_type)
            return f"{field}: {data}\n"
        if data_type == "binary":
            return f"{field}: 0b{data}\n"
        if data_type == "hexadecimal":
            return f"{field}: 0x{data}\n"
        raise ValueError("Unrecognized data type for human readable output formatting!")

    def format_json_data(
        self, field: str, data: str, data_type: str, format_type: str
    ) -> Dict[str, Union[str, int]]:
        """Formats and returns a dictionary for a field based on the specified formatting"""
        if format_type == "decimal":
            int_data = self.datastring_to_decimal(data, data_type)
            return {field: int_data}
        if format_type == "decimal*5":
            int_data = self.datastring_to_decimal(data, data_type) * 5
            return {field: int_data}
        if format_type == "decimal*5+5":
            int_data = self.datastring_to_decimal(data, data_type) * 5 + 5
            return {field: int_data}
        if format_type == "decimal*100":
            int_data = self.datastring_to_decimal(data, data_type) * 100
            return {field: int_data}
        if format_type == "uppercase":
            return {field: data.upper()}
        if format_type == "timestamp":
            return {field: self.format_timestamp_output(data, data_type)}
        if data_type == "binary":
            return {field: f"0b{data}"}
        if data_type == "hexadecimal":
            return {field: f"0x{data}"}
        raise ValueError("Unrecognized data type for json output formatting!")

    def has_json_field(self, schema: Dict[str, Union[str, list]]) -> bool:
        """Returns true if at least one instruction in the schema has a json field"""
        instructions = schema.get("instructions", [])
        for instruction in instructions:
            if "json_field" in instruction:
                return True
        return False

    def extract_humanreadable_output(
        self,
        schema: Dict[str, Union[str, list]],
        bytelist: List[str],
        verbose: bool = False,
        depth: int = 0,
    ) -> str:
        """Processes the complete schema and returns a human-readble output string"""
        output = ""
        if schema["schema_level"] == "byte":
            for instruction in schema["instructions"]:
                verbose_only_field = instruction.get("verbose_only", False)
                if not verbose and verbose_only_field:
                    continue
                field_name = instruction["field"]
                format_type = instruction.get("format", "")
                offset = instruction["offset"]
                size = instruction["size"]
                subschema = instruction.get("subschema", {})
                field_bytelist = bytelist[offset : offset + size]
                field_bytestring = self.bytelist_to_bytestring(
                    field_bytelist, little_endian=True
                )  # Assuming always little endian
                output += self.format_humanreadable_output_prefix(depth)
                if subschema and not verbose:
                    output += f"{field_name}:\n"
                else:
                    output += self.format_humanreadable_instruction_output(
                        field_name, field_bytestring, "hexadecimal", format_type
                    )
                if subschema:
                    output += self.extract_humanreadable_output(
                        subschema, field_bytelist, verbose, depth + 1
                    )
        elif schema["schema_level"] == "bit":
            bytestring = self.bytelist_to_bytestring(
                bytelist, little_endian=True
            )  # Assuming always little endian
            bitstring = bin(int(bytestring, 16))[2:].zfill(len(bytelist) * 8)
            for instruction in schema["instructions"]:
                verbose_only_field = instruction.get("verbose_only", False)
                if not verbose and verbose_only_field:
                    continue
                field_name = instruction["field"]
                format_type = instruction.get("format", "")
                offset = instruction["offset"]
                size = instruction["size"]
                field_bitstring = bitstring[
                    len(bitstring) - offset - size : len(bitstring) - offset
                ]
                output += self.format_humanreadable_output_prefix(depth)
                output += self.format_humanreadable_instruction_output(
                    field_name, field_bitstring, "binary", format_type
                )
        else:
            raise ValueError("Unrecognized schema level!")
        return output

    def extract_json_output(
        self, schema: Dict[str, Union[str, list]], bytelist: List[str]
    ) -> Dict[str, Union[str, int, dict]]:
        """Processes the complete schema and returns an output dictionary"""
        output_dict = {}
        if schema["schema_level"] == "byte":
            for instruction in schema["instructions"]:
                field_name = instruction.get("json_field", "")
                if field_name:
                    format_type = instruction.get("json_format", "")
                    offset = instruction["offset"]
                    size = instruction["size"]
                    subschema = instruction.get("subschema", {})
                    field_bytelist = bytelist[offset : offset + size]
                    field_bytestring = self.bytelist_to_bytestring(
                        field_bytelist, little_endian=True
                    )  # Assuming always little endian
                    if subschema and self.has_json_field(subschema):
                        field_data = self.extract_json_output(subschema, field_bytelist)
                        output_dict[field_name] = field_data
                    else:
                        output_dict.update(
                            self.format_json_data(
                                field_name, field_bytestring, "hexadecimal", format_type
                            )
                        )
        elif schema["schema_level"] == "bit":
            bytestring = self.bytelist_to_bytestring(
                bytelist, little_endian=True
            )  # Assuming always little endian
            bitstring = bin(int(bytestring, 16))[2:].zfill(len(bytelist) * 8)
            for instruction in schema["instructions"]:
                field_name = instruction.get("json_field", "")
                if field_name:
                    format_type = instruction.get("json_format", "")
                    offset = instruction["offset"]
                    size = instruction["size"]
                    field_bitstring = bitstring[
                        len(bitstring) - offset - size : len(bitstring) - offset
                    ]
                    output_dict.update(
                        self.format_json_data(
                            field_name, field_bitstring, "binary", format_type
                        )
                    )
        else:
            raise ValueError("Unrecognized schema level!")
        return output_dict


def main():
    """Executes this python file as a standalone tool"""
    parser = argparse.ArgumentParser(description="Latency Monitor Log Parser")
    parser.add_argument(
        "inputfile",
        help="The input file containing Latency Monitor hexdump collected using nvme-get-log. If the input file is a raw binary file, use the -b flag.",
    )
    parser.add_argument(
        "-s",
        "--schemafile",
        help="Optional argument to use a custom schema. Uses OCP Datacenter NVMe SSD Specification 2.0 if not specified.",
    )
    parser.add_argument(
        "-o",
        "--outputformat",
        choices=["text", "json"],
        default="text",
        help="Optional argument to change output format. Outputs human readable text if not specified.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Optional argument to display extended information in human readable text output.",
    )
    parser.add_argument(
        "-b",
        "--raw-binary",
        action="store_true",
        help="Optional argument to specify that the input file is a raw binary file. Assumes hexdump input file if not specified.",
    )
    args = parser.parse_args()

    lmparser = LatencyMonitorLogParser()

    if args.schemafile:
        schemafile = open(args.schemafile)
        schema = json.load(schemafile)
        schemafile.close()
    else:
        schema = lmparser.OCP2_SCHEMA

    if args.raw_binary:
        inputfile = open(args.inputfile, "rb")
        inputfiledata = inputfile.read()
        bytelist = inputfiledata.hex(" ", 1).split()
    else:
        inputfile = open(args.inputfile, "rt")
        inputfiledata = inputfile.read()
        byteregex = r"(?<!\S)[0-9a-fA-F]{2}(?!\S)"
        bytelist = re.findall(byteregex, inputfiledata)
    inputfile.close()

    if args.outputformat == "text":
        output = lmparser.extract_humanreadable_output(schema, bytelist, args.verbose)
        print(output)
    elif args.outputformat == "json":
        output_dict = lmparser.extract_json_output(schema, bytelist)
        output = json.dumps(output_dict, indent=4, separators=(",", ": "))
        print(output)
    else:
        raise ValueError("Unrecognized output format!")


if __name__ == "__main__":
    main()
