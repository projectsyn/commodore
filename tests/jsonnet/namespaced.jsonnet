local com = import 'lib/commodore.libjsonnet';

{
  ns1: com.namespaced(
    'test',
    {
      metadata: {
        annotations: {
          a: '1',
        },
      },
    }
  ),
  ns2: com.namespaced(
    'test',
    { metadata: { namespace: 'other' } }
  ),
}
