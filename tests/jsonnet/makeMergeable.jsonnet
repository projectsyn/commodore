local com = import 'lib/commodore.libjsonnet';

{
  o0: { base: { v: 'value' } } + { base: { v2: 'test' } },
  o1: { base: { v: 'value' } } + com.makeMergeable({ base: { v2: 'test' } }),
  o2: {
    base: 'value',
    nestedArr: [ 1, 2, 3 ],
    nestedObj: { a: 'aaa' },
  } + com.makeMergeable({
    base: 'test',
    nestedArr: [ 4 ],
    nestedObj: {
      b: 'bbb',
    },
  }),
}
