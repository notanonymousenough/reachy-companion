import unittest
from unittest.mock import patch
from types import SimpleNamespace
from reachy_companion.firewall import render, active_ap_interfaces, sync_recovery
from reachy_companion.firewall import main

class LocalFirewallTests(unittest.TestCase):
    def setUp(self):
        self.config={'security':{'robot':{'policy':'local_ssh','nft_table':'reachy_companion',
                      'service':'reachy-companion-firewall','rollback_seconds':180}}}

    def test_client_network_never_exposes_factory_or_agent(self):
        rules=render(self.config,recovery_interfaces=[])
        self.assertIn('tcp dport 22 accept',rules)
        self.assertNotIn('ip saddr',rules)
        self.assertNotIn('ip6 saddr',rules)
        self.assertNotIn('8090',rules)
        self.assertNotIn('elements =',rules)
        for line in rules.splitlines():
            if '8000' in line or '8443' in line or 'udp dport 67' in line:
                self.assertIn('iifname @recovery_interfaces',line)

    def test_hotspot_has_server_and_client_dhcp_and_both_ip_families(self):
        rules=render(self.config,recovery_interfaces=['wlan0'])
        self.assertIn('elements = { "wlan0" }',rules)
        self.assertIn('udp sport 68 udp dport 67 accept',rules)
        self.assertIn('udp sport 67 udp dport 68 accept',rules)
        self.assertIn('udp sport 547 udp dport 546 accept',rules)
        self.assertIn('ip6 daddr ff02::fb',rules)
        self.assertNotIn('flush ruleset',rules)

    @patch('reachy_companion.firewall.subprocess.run')
    def test_ap_role_detected_from_networkmanager_not_network_name(self,run):
        run.side_effect=[SimpleNamespace(returncode=0,stdout='abc:802-11-wireless:wlan0\n'),
                         SimpleNamespace(returncode=0,stdout='ap\n')]
        self.assertEqual(active_ap_interfaces(),['wlan0'])
        run.side_effect=[SimpleNamespace(returncode=0,stdout='abc:802-11-wireless:wlan0\n'),
                         SimpleNamespace(returncode=0,stdout='infrastructure\n')]
        self.assertEqual(active_ap_interfaces(),[])

    @patch('reachy_companion.firewall.subprocess.run',side_effect=OSError)
    def test_missing_networkmanager_fails_closed(self,run):
        self.assertEqual(active_ap_interfaces(),[])

    def test_no_rule_injection_from_interface(self):
        with self.assertRaises(ValueError):render(self.config,recovery_interfaces=['wlan0"; accept'])

    @patch.dict('os.environ',{'REACHY_FIREWALL_ACTION':'down','REACHY_FIREWALL_IFACE':'wlan0'})
    @patch('reachy_companion.firewall.run')
    @patch('reachy_companion.firewall.active_ap_interfaces',return_value=['wlan0'])
    @patch('reachy_companion.firewall.subprocess.run',return_value=SimpleNamespace(returncode=0))
    def test_down_event_closes_hotspot_even_before_nm_updates_state(self,subprocess,aps,run):
        sync_recovery(self.config)
        self.assertEqual(run.call_args.kwargs['input'],'flush set inet reachy_companion recovery_interfaces\n')

    @patch('reachy_companion.firewall.Path')
    @patch('reachy_companion.firewall.run')
    @patch('reachy_companion.firewall.subprocess.run',return_value=SimpleNamespace(returncode=3))
    def test_rearming_cancels_previous_timer_before_scheduling_another(self,process,run,path):
        previous='reachy-companion-firewall-rollback-'+'a'*32
        path.return_value.exists.return_value=True
        path.return_value.read_text.return_value=previous
        main(self.config,'arm')
        self.assertEqual(run.call_args_list[0].args,('systemctl','stop',previous+'.timer'))
        self.assertEqual(run.call_args_list[1].args[0],'systemd-run')

    @patch('reachy_companion.firewall.Path')
    @patch('reachy_companion.firewall.run')
    @patch('reachy_companion.firewall.subprocess.run',return_value=SimpleNamespace(returncode=0))
    def test_rearming_refuses_a_rollback_already_running(self,process,run,path):
        path.return_value.exists.return_value=True
        path.return_value.read_text.return_value='reachy-companion-firewall-rollback-'+'a'*32
        with self.assertRaises(RuntimeError):main(self.config,'arm')
        run.assert_not_called()

    @patch('reachy_companion.firewall.Path')
    @patch('reachy_companion.firewall.run')
    @patch('reachy_companion.firewall.subprocess.run',return_value=SimpleNamespace(returncode=3))
    def test_expired_timer_cannot_be_confirmed(self,process,run,path):
        path.return_value.read_text.return_value='reachy-companion-firewall-rollback-'+'a'*32
        with self.assertRaises(RuntimeError):main(self.config,'confirm')
        run.assert_not_called()
