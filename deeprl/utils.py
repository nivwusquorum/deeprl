import json
import os
import tensorflow as tf

def import_class(path):
    path_split = path.split('.')
    # TODO(szymon): understand Python imports better

    # try to import entire module and then get class as an attribute
    try:
        module_name, class_name = '.'.join(path_split[:-1]), path_split[-1]
        module = __import__(module_name, fromlist=(class_name,))
        return getattr(module, class_name)
    except ImportError:
        pass

    # try to import only the main module and the getattr your way down.
    module_or_class = __import__(path_split[0], globals(), locals())
    for name in path_split[1:]:
        module_or_class = getattr(module_or_class, name)
    return module_or_class

def ensure_json(something):
    if isinstance(something, str):
        with open(something, "rt") as f:
            return json.load(f)
    elif hasattr(something, "read"):
        return json.load(something)
    else:
        return something

def nps_to_bytes(arrays):
    memfile = BytesIO()
    memfile.write(('%d\n' % (len(arrays),)).encode('ascii'))
    for a in arrays:
        np.save(memfile, a)
    memfile.seek(0)
    b = memfile.read()
    return b

def bytes_to_nps(b):
    memfile = BytesIO(b)
    n_arrays = int(memfile.readline())
    return [np.load(memfile) for _ in range(n_arrays)]

def ensure_directory(path):
    if not os.path.exists(path):
        os.makedirs(path)

def make_session(max_cpu_cores=None):
    """Makes a multi-core session.
    If max_cpu_cores is None, it adopts the number of cores
    automatically
    """
    config = tf.ConfigProto()

    if max_cpu_cores is not None:
        config.device_count.update({'CPU': max_cpu_cores})

    return tf.Session(config=config)
