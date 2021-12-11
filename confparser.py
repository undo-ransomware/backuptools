# parser for systemd-style config file format
# not the configparser library because we really need repeatable options for the exclude= option
from collections import defaultdict
from datetime import timedelta
import re

class ConfigParser:
	def __init__(self, host, space):
		if ':' in host:
			raise ConfigException('colons not permitted in hostname %s' % host)
		self.keys = dict()
		self.host = host
		self.space = '%s:%s' % (host, space)

	def __getitem__(self, key):
		return self._get(key, self.host, self.space)

	def get(self, section, key):
		return self._get(key, section, None)

	def _get(self, key, host, space):
		if key not in self.keys:
			raise ConfigException('unknown config key %s' % key)
		default, converter, initial, appender = self.keys[key]

		if key in self.values[space]:
			value = self.values[space][key]
		elif key in self.values[host]:
			value = self.values[host][key]
		elif key in self.values['global']:
			value = self.values['global'][key]
		else:
			value = default
		return value

	def sections(self):
		return [ tuple(sect.split(':', 1)) if ':' in sect else (sect, None) for sect in self._sections ]

	def _timedelta(value):
		if value.endswith('w'):
			return timedelta(weeks=int(value[:-1]))
		if value.endswith('d'):
			return timedelta(days=int(value[:-1]))
		if value.endswith('h'):
			return timedelta(hours=int(value[:-1]))
		if value.endswith('m'):
			return timedelta(minutes=int(value[:-1]))
		if value.endswith('s'):
			return timedelta(seconds=int(value[:-1]))
		raise ConfigException('time unit missing in %s' % value)

	def _single_value(key, old, new):
		if old is not None:
			raise ConfigException('cannot repeat option %s' % key)
		return new

	def add_key(self, key, default=None, converter=str, initial=None, appender=_single_value):
		self.keys[key] = (converter(default) if isinstance(default, str) else default, converter, initial, appender)

	def add_str(self, *args, **kwargs):
		self.add_key(*args, converter=str, **kwargs)

	def add_int(self, *args, **kwargs):
		self.add_key(*args, converter=int, **kwargs)

	def add_timedelta(self, *args, **kwargs):
		self.add_key(*args, converter=ConfigParser._timedelta, **kwargs)

	def add_list(self, *args, **kwargs):
		self.add_key(*args, initial=[], appender=lambda key, old, new: old + [new], **kwargs)

	def parse(self, fd):
		self.values = defaultdict(dict)
		self._sections = list()
		section = None
		for line in fd:
			line = line.rstrip('\r\n')
			if line.lstrip().startswith('#'):
				continue
			if line.strip() == '':
				continue

			if line.startswith('[') and line.endswith(']'):
				section = line[1:-1]
				if section != 'global':
					self._sections.append(section)
				continue
			if '=' not in line:
				raise ConfigException('missing value for option %s' % line)
			key, value = line.split('=', 1)

			if key not in self.keys:
				raise ConfigException('unknown option %s' % key)
			default, converter, initial, appender = self.keys[key]
			sect = self.values[section]
			old = sect[key] if key in sect else initial
			sect[key] = appender(key, old, converter(value))

class ConfigException(Exception):
	pass

if __name__ == '__main__':
	parser = ConfigParser('localhost', 'root')
	parser.add_str('test')
	parser.add_int('foo', 123)
	parser.add_str('bar', 'baz')
	parser.add_list('exclude')
	parser.add_timedelta('cooldown', timedelta(milliseconds=500))

	parser.parse([' ## comment', ' \r\n', '', '[global]'])
	assert parser['test'] is None
	assert parser['foo'] == 123
	assert parser['bar'] == 'baz'
	assert parser['exclude'] is None
	assert parser['cooldown'] == timedelta(milliseconds=500)
	assert parser.sections() == []

	parser.parse(['[global]', 'test= value ', 'foo=1', 'bar=', 'exclude=/tmp', 'exclude=/var/tmp', 'cooldown=1d'])
	assert parser['test'] == ' value '
	assert parser['foo'] == 1
	assert parser['bar'] == ''
	assert parser['exclude'] == ['/tmp', '/var/tmp']
	assert parser['cooldown'] == timedelta(days=1)
	assert parser.sections() == []

	parser.parse(['[global]', 'test=glob', 'bar=barf', 'exclude=/tmp', 'exclude=/var/tmp', '[localhost]', 'test=local',
			'cooldown=3m', '[localhost:root]', 'exclude=/bin/bash', 'cooldown=15s'])
	assert parser['test'] == 'local'
	assert parser['foo'] == 123
	assert parser['bar'] == 'barf'
	assert parser['exclude'] == ['/bin/bash']
	assert parser['cooldown'] == timedelta(seconds=15)
	assert parser.get('localhost', 'cooldown') == timedelta(minutes=3)
	assert parser.sections() == [('localhost', None), ('localhost', 'root')]
