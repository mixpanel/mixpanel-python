#!/usr/bin/env python
import urllib
import unittest
import mixpanel

class MixpanelTestCase(unittest.TestCase):
    def setUp(self):
        print "set up"

    def tearDown(self):
        print "tear down"

    def test_constructor(self):
        mp = mixpanel.Mixpanel()

    def test_track1(self):
        mp = mixpanel.Mixpanel("1234")
        mp.track("pushed button", {"color": "blue", "weight": "5lbs"})    

    def test_track2(self):
        mp = mixpanel.Mixpanel("1234")
        mp.track("event2", {"x": "y", "poppin": "tags", "ip": "something"})

    # woo this test actually passes
    def test_identify(self):
        mp = mixpanel.Mixpanel("1234")
        mp.identify("2345")
        self.assertEqual(mp._distinct_id, "2345")

if __name__ == "__main__":
    unittest.main()
