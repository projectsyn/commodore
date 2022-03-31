local com = import 'lib/commodore.libjsonnet';

std.sort(com.list_dir(std.extVar('work_dir')))
