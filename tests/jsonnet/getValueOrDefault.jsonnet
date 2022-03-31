local com = import 'lib/commodore.libjsonnet';

local data = {
  a: 1,
  b: 'bbb',
  c: [ 1, 2, 3 ],
  d: {
    e: {
      f: {
        g: 'ggg',
      },
      h: 'hhh',
    },
  },
};

{
  v1: com.getValueOrDefault(data, 'a', '1'),
  v2: com.getValueOrDefault(data, 'A', '1'),
}
