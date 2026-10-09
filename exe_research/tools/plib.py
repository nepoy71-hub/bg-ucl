from lib import *
import struct as _s
P=_p=open('/mnt/user-data/uploads/Claude outputs/PES2021_prot.bin','rb').read()
_n=_s.unpack_from('<I',_p,4)[0]
PR=[_s.unpack_from('<QQQ',_p,8+i*24) for i in range(_n)]
def pget(va,n):
    for a,sz,off in PR:
        if a<=va<a+sz: return _p[off+va-a:off+va-a+n]
    o=va2off(va)
    return d[o:o+n] if o is not None else None
def pdis(va,n=40,stop=True):
    b=pget(va,n*15); out=[]
    for i in md.disasm(b,va):
        out.append('%x: %-8s %s'%(i.address,i.mnemonic,i.op_str)); n-=1
        if n<=0 or (stop and i.mnemonic in('ret','int3')): break
    return out
import numpy as _np
_PT=[]
for _a,_sz,_off in PR:
    _raw=P[_off:_off+_sz]; _buf=_np.frombuffer(_raw,dtype=_np.uint8)
    _b=[_buf[k:len(_buf)-3+k].astype(_np.int64) for k in range(4)]
    _d=(_b[0]|(_b[1]<<8)|(_b[2]<<16)|(_b[3]<<24)); _d=_np.where(_d>=2**31,_d-2**32,_d)
    _PT.append((_a,_d+_np.arange(len(_d),dtype=_np.int64)+_a+4))
def pxrefs(va):
    out=[]
    for a,t in _PT:
        out+=[a+int(i) for i in _np.nonzero(t==va)[0]]
    return out
