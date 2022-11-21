// Injects a deprecation message into all kube.libsonnet fields.
// The message is not yet used. But cna be enabled with
// local kube = (import 'lib/kube.libjsonnet') { _commodore_show_kube_libsonnet_deprecation:: true };

local deprecationWarning = |||
  Usage of `kube.lib(j)sonnet` is deprecated.

  It will be replaced by https://github.com/jsonnet-libs/k8s-libsonnet in the future, which auto generates the library from the OpenAPI spec.

  Used `kube.%s`.
|||;

local kube = import 'lib/kube-libsonnet/kube.libsonnet';

{
  _commodore_show_kube_libsonnet_deprecation:: false,
}
+
{
  [key]: if super._commodore_show_kube_libsonnet_deprecation then
    std.trace(deprecationWarning % key, std.get(kube, key))
  else
    std.get(kube, key)
  for key in std.objectFieldsAll(kube)
}
