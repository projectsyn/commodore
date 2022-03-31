local com = import 'lib/commodore.libjsonnet';

local fixup(obj) =
  obj {
    metadata+: {
      annotations+: {
        patched: 'true',
      },
    },
  };

com.fixupDir(std.extVar('work_dir'), fixup)
