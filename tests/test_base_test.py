"""
====================================================

QuantEngine

Base Test Case

====================================================
"""

import unittest

from core.pipeline.pipeline_context import PipelineContext


class BaseTestCase(unittest.TestCase):

    def setUp(self):

        self.context = PipelineContext()

    # -------------------------------------------------

    def assertFloatEqual(

        self,

        a,

        b,

        places=6,

    ):

        self.assertAlmostEqual(

            a,

            b,

            places=places,

        )

    # -------------------------------------------------

    def assertValidPrice(

        self,

        price,

    ):

        self.assertGreaterEqual(

            price,

            0.0,

        )

    # -------------------------------------------------

    def assertPositive(

        self,

        value,

    ):

        self.assertGreater(

            value,

            0.0,

        )