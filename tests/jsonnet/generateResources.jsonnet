local com = import 'lib/commodore.libjsonnet';

local input = {
  obj1: { spec: { a: 1, b: 2 } },
  obj2: null,
};

local objFn(name) = {
  metadata: {
    name: name,
  },
};

com.generateResources(input, objFn)
