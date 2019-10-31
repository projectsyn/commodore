local com = import 'lib/commodore.libjsonnet';
local chart_output_dir = std.extVar('chart_output_dir');
local namespace = std.extVar('namespace');

com.addNamespaceToHelmOutput(chart_output_dir, namespace)
