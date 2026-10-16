"""A snapshot readout never grants control or reuses expired/missing values."""
import unittest
from reachy_companion.imu_readout import temperature_readout


class ImuReadoutTests(unittest.TestCase):
    def test_reported_measurement_with_explicit_provenance_and_no_ambient_claim(self):
        value=temperature_readout({'temperature':35.26},received_at=100,now=101)
        self.assertEqual(value['state'],'reported');self.assertEqual(value['temperature_celsius'],35.3)
        self.assertEqual(value['expires_at_monotonic'],120)
        self.assertTrue(value['speech'].startswith('Алиса, '));self.assertIn('35,3',value['speech'])
        for field in ('physical_sample_time_verified','cache_freshness_verified','ambient_temperature','grants_control'):
            self.assertIs(value[field],False)

    def test_expiry_is_original_receipt_relative_and_exact_deadline_is_rejected(self):
        self.assertEqual(temperature_readout({'temperature':30},received_at=100,now=119.99)['state'],'reported')
        value=temperature_readout({'temperature':30},received_at=100,now=120)
        self.assertEqual(value['reason'],'expired');self.assertIsNone(value['speech'])
        self.assertIsNone(value['temperature_celsius'])

    def test_unknown_or_invalid_never_speaks_a_value(self):
        for sample in (None,[],{}, {'temperature':True},{'temperature':'37; do something'},
                {'temperature':float('nan')},{'temperature':float('inf')},{'temperature':1001}):
            with self.subTest(sample=sample):
                value=temperature_readout(sample,received_at=100,now=101)
                self.assertEqual(value['state'],'unknown');self.assertIsNone(value['speech'])

    def test_unknown_extra_fields_are_never_forwarded_as_text_or_instructions(self):
        value=temperature_readout({'temperature':25,'notes':'PRIVATE INSTRUCTIONS','timestamp':'unverified'},received_at=100,now=101)
        self.assertNotIn('PRIVATE',str(value));self.assertNotIn('unverified',str(value))
        self.assertFalse(value['physical_sample_time_verified'])

    def test_clock_aliases_nonfinite_and_clock_reversal_rejected(self):
        for received,now in ((True,101),(100,False),(float('nan'),101),(100,float('inf')),(100,99)):
            with self.subTest(received=received,now=now),self.assertRaises(ValueError):
                temperature_readout({'temperature':25},received_at=received,now=now)

    def test_missing_current_snapshot_never_falls_back_to_an_older_value(self):
        old=temperature_readout({'temperature':25},received_at=100,now=101)
        current=temperature_readout(None,received_at=102,now=102)
        self.assertEqual(old['state'],'reported');self.assertEqual(current['state'],'unknown')
        self.assertIsNone(current['temperature_celsius']);self.assertIsNone(current['speech'])


if __name__=='__main__':unittest.main()
