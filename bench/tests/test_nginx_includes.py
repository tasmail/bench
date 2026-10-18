"""Offline coverage of native nginx regeneration; no services or listeners."""

import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bench.config.nginx import make_bench_manager_nginx_conf, make_nginx_conf


class TestNginxServerInclude(unittest.TestCase):
	def setUp(self):
		self.temp = tempfile.TemporaryDirectory()
		self.addCleanup(self.temp.cleanup)
		self.path = Path(self.temp.name)
		(self.path / "config").mkdir()
		self.config = {
			"nginx_server_include": "/etc/nginx/http-security-edge-server.conf"
		}
		self.sites = {
			"that_use_dns": ["example.test"],
			"that_use_wildcard_ssl": ["*.example.test"],
			"wildcard_ssl_certificate": "/fixture/cert.pem",
			"wildcard_ssl_certificate_key": "/fixture/key.pem",
			"that_use_ssl": [
				{
					"name": "tls.example.test",
					"ssl_certificate": "/fixture/cert.pem",
					"ssl_certificate_key": "/fixture/key.pem",
				}
			],
			"that_use_port": [{"name": "port.example.test", "port": 8080}],
			"domain_map": {},
		}

	def generate(self):
		with (
			patch(
				"bench.config.nginx.Bench",
				return_value=SimpleNamespace(conf=self.config),
			),
			patch("bench.config.nginx.prepare_sites", return_value=self.sites),
			patch("bench.config.nginx.get_bench_name", return_value="fixture-bench"),
		):
			make_nginx_conf(str(self.path), yes=True)
		return (self.path / "config/nginx.conf").read_text()

	def test_include_survives_regeneration_and_new_sites(self):
		for _ in range(2):
			text = self.generate()
			self.assertEqual(len(re.findall(r"(?m)^\s*server\s*\{", text)), 6)
			self.assertEqual(
				text.count("include /etc/nginx/http-security-edge-server.conf;"), 6
			)
		self.sites["that_use_ssl"].append(
			{
				"name": "new.example.test",
				"ssl_certificate": "/fixture/cert.pem",
				"ssl_certificate_key": "/fixture/key.pem",
			}
		)
		self.assertEqual(
			self.generate().count("include /etc/nginx/http-security-edge-server.conf;"),
			8,
		)

	def test_disabled_by_default(self):
		self.config.clear()
		self.assertNotIn("http-security", self.generate())

	def test_invalid_include_does_not_overwrite_existing_configuration(self):
		previous = self.generate()
		for value in [
			True,
			[],
			"relative.conf",
			"/etc/nginx/a.conf; return 200;",
			"/tmp/a\n.conf",
			"/etc/../a.conf",
			"/tmp/$host.conf",
			"/tmp/*.conf",
		]:
			with self.subTest(value=value):
				self.config["nginx_server_include"] = value
				with self.assertRaises(ValueError):
					self.generate()
				self.assertEqual(
					(self.path / "config/nginx.conf").read_text(), previous
				)

	def test_manager_append_uses_same_opt_in(self):
		with (
			patch(
				"bench.config.nginx.Bench",
				return_value=SimpleNamespace(conf=self.config),
			),
			patch("bench.config.nginx.get_bench_name", return_value="fixture-bench"),
			patch("bench.config.site_config.get_site_config", return_value={}),
		):
			make_bench_manager_nginx_conf(
				str(self.path), yes=True, domain="manager.example.test"
			)
		self.assertIn(
			"include /etc/nginx/http-security-edge-server.conf;",
			(self.path / "config/nginx.conf").read_text(),
		)
