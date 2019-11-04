local com = import 'lib/commodore.libjsonnet';
local kube = import 'lib/kube.libjsonnet';
local chart_output_dir = std.extVar('chart_output_dir');
local namespace = std.extVar('namespace');
local create_namespace = std.extVar('create_namespace');

com.addNamespaceToHelmOutput(chart_output_dir, namespace) +
if create_namespace == "true" then {'00_namespace': kube.Namespace(namespace)} else {}
