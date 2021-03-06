"""
this is a hack due we couldn't compile the fortran code using gfortran.
"""
import sys
import os.path
import tempfile
import cStringIO
from collections import Iterable

try:
    import subprocess32 as subprocess
    TIME_OUT = True
except ImportError:
    import subprocess
    TIME_OUT = False

import numpy as np
from django.template.loader import render_to_string
from eos import get_eos
from sur import data




def exec_fortran(bin, path, as_out_txt=None, timeout=10):
    """Execute a fortran program
    if as_out_txt is read that file and return its content
    """

    args = []
    if sys.platform != 'win32':
        # On any non-Windows system, we run binaries through wine
        args.append('wine')
    args.append(data(bin + '.exe'))

    if TIME_OUT:
        p = subprocess.Popen(args, cwd=path, stdout=subprocess.PIPE)
        output = p.communicate(timeout=timeout)[0]
    else:
        p = subprocess.Popen(args, cwd=path, stdout=subprocess.PIPE)
        output = p.communicate()[0]
    if as_out_txt:
        txt = os.path.join(path, as_out_txt)
        with open(txt, 'r') as fh:
            output = fh.read()

    return output


def write_input(mixture, eos, t=None, p=[], v=[], ii=None,
                as_data=False, interactions=None, **kwargs):
    """
    if t and p are given, return the path of the folder with
    a written flashIN.txt
    """

    compounds = []
    if p and not isinstance(p, Iterable):
        p = [p]
    if v and not isinstance(v, Iterable):
        v = [v]
    for i, c in enumerate(mixture.compounds):
        if i > 0:
            for k, matrix in interactions.items():
                setattr(c, '%s_' % k, "   ".join(map(str, matrix[:i, i])))
        update = eos == 'RKPR'
        c.params = "   ".join(map(str, c._get_eos_params(eos, update_vc=update)))
        compounds.append(c)
    nTdep = 1 if 'k0' in interactions else 0
    eos = get_eos(eos)
    kw = locals().copy()
    kw.update(kwargs)
    data = render_to_string('input.html', kw)
    if as_data:
        return data

    input_file = 'flashIN.txt' if (t and (p or v) or ii) else 'envelIN.txt'
    path = tempfile.mkdtemp()
    with open(os.path.join(path, input_file), 'w') as fh:
        fh.write(data)

    return path


def envelope(env):
    path = write_input(env.mixture, env.setup.eos, interactions=env.interactions)
    output = exec_fortran('EnvelopeSur', path, as_out_txt="envelOUT.txt",
                          timeout=len(env.mixture) + 2)
    # to debug
    env.input_txt = open(os.path.join(path, 'envelIN.txt')).read()
    env.output_txt = output
    output = output.split('\n')

    mark = "    T(K)        P(bar)        D(mol/L)"
    for start, line in enumerate(output):
        if line.startswith(mark):
            break

    env_block = []
    for end, line in enumerate(output[start + 1:]):
        if not line.strip():
            break
        env_block.append(line)

    env_block = np.loadtxt(cStringIO.StringIO("\n".join(env_block)),
                           unpack=True, ndmin=2)

    for start_cri, line in enumerate(output[start + end:]):
        if line.startswith(mark):
            break

    cri_block = output[start + end + start_cri + 1:]
    cri_block = np.loadtxt(cStringIO.StringIO("\n".join(cri_block)),
                           unpack=True, ndmin=2)
    if not cri_block.any():
        cri_block = [None, None, None, None]
    return env_block, cri_block


def flash(fi):
    path = write_input(fi.mixture, fi.setup.eos, fi.t, fi.p, fi.v,
                       interactions=fi.interactions, nplus=len(fi.mixture))
    output = exec_fortran('FlashSur', path)

    # to debug
    fi.input_txt = open(os.path.join(path, 'flashIN.txt')).read()
    fi.output_txt = output
    output = [float(n) for n in output.replace('\r\n', '').split()]
    n = len(fi.mixture)
    x, y, (rho_x, rho_y, beta_mol, beta_vol, p, v) = output[:n], output[n:-6], output[-6:]

    x = np.array(x)
    y = np.array(y)
    return x / x.sum(), y / y.sum(), rho_x, rho_y, beta_mol, beta_vol, p, v


def isochore(ii):
    path = write_input(ii.mixture, ii.setup.eos, ii=ii, interactions=ii.interactions, nplus=len(ii.mixture))
    output = exec_fortran('FlashSur', path)

    # to debug
    ii.input_txt = open(os.path.join(path, 'flashIN.txt')).read()
    ii.output_txt = open(os.path.join(path, 'flashPvbeta.txt')).read()
    raw_data = ii.output_txt.split('\r\n')
    separator = raw_data.index('    T(K)   rho(mol/L)   P(bar)    v(L/mol) ')
    main_block = cStringIO.StringIO('\n'.join(raw_data[3:separator-1]))
    mono_block = cStringIO.StringIO('\n'.join(raw_data[separator+1:]))

    ii.t, ii.rho, ii.p, ii.beta_mol, ii.beta_vol = np.loadtxt(main_block,
                                                             unpack=True, usecols=[0, 1, 2, 4, 5])

    ii.t_monophasic, ii.rho_monophasic, ii.p_monophasic = np.loadtxt(mono_block,
                                                                     unpack=True, usecols=[0, 1, 2])



def multiflash(mixture, setup, t, p, v):

    path = write_input(mixture, setup.eos, t, p, v, interactions=setup.get_interactions(mixture))
    output = exec_fortran('FlashSur', path)

    flashes_data = []

    n = len(mixture)
    o = output.split()
    for flash_data in zip(*[iter(o)]*(2*n + 6)):
        output = [float(n_) for n_ in ' '.join(flash_data).split()]
        x, y, (rho_x, rho_y, beta_mol, beta_vol, p, v) = output[:n], output[n:-6], output[-6:]
        x = np.array(x)
        y = np.array(y)
        flashes_data.append((x / x.sum(), y / y.sum(), rho_x, rho_y, beta_mol, beta_vol, p, v))
    return flashes_data
