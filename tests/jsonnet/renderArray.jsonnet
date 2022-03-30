local com = import 'lib/commodore.libjsonnet';

{
  a1: com.renderArray([ 'a', 'b', 'c', '~b', 'c' ]),
  a2: com.renderArray([ 'a', 'b', 'c', '~b', 'c', 'b' ]),
  a3: com.renderArray([ 'c', 'a' ]),
}
