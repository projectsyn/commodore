local com = import 'lib/commodore.libjsonnet';

local work_dir = std.extVar('work_dir');

{
  f0: com.yaml_load(work_dir + '/test0.yaml'),
  f1: com.yaml_load_all(work_dir + '/test1.yaml'),
  f2: com.yaml_load_all(work_dir + '/test2.yaml'),
}
