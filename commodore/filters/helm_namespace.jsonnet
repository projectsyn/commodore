local com = import 'lib/commodore.libjsonnet';
local kube = import 'lib/kube.libjsonnet';
local chart_output_dir = std.extVar('chart_output_dir');
local namespace = std.extVar('namespace');
local create_namespace = std.extVar('create_namespace');
local exclude_objstr = std.extVar('exclude_objects');
local exclude_objstrs =
  std.filter(function(s) std.length(s) > 0, std.split(exclude_objstr, '|'));
local exclude_objs =
  std.map(function(e) std.parseJson(e), exclude_objstrs);

com.addNamespaceToHelmOutput(chart_output_dir, namespace, exclude_objs) +
if create_namespace == "true" then {'00_namespace': kube.Namespace(namespace)} else {}
