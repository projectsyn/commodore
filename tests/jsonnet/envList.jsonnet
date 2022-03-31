local com = import 'lib/commodore.libjsonnet';

com.envList({
  VAR1: 'aaa',
  VAR2: { configMapRef: { name: 'test', key: 'var2' } },
  VAR3: null,
})
