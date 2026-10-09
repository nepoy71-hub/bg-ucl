import struct,re,numpy as np
from capstone import *
d=open('/mnt/user-data/uploads/Claude outputs/PES2021_code.bin','rb').read()
BASE=0x140000000
secs=[('.trace',0x1000,0x252d800,0x600),('.rdata',0x252f000,0xe6bc00,0x252de00),('.data',0x339b000,0x334800,0x3399a00)]
def off2va(o):
    for n,va,rs,rp in secs:
        if rp<=o<rp+rs: return BASE+va+o-rp
def va2off(v):
    v-=BASE
    for n,va,rs,rp in secs:
        if va<=v<va+rs: return rp+v-va
T0,TN=0x600,0x252d800
code=np.frombuffer(d,dtype=np.uint8,count=TN,offset=T0)
_b=[code[i:TN-3+i].astype(np.uint32) for i in range(4)]
disp=(_b[0]|(_b[1]<<8)|(_b[2]<<16)|(_b[3]<<24)).astype(np.int32).astype(np.int64)
tgt=disp+np.arange(TN-3,dtype=np.int64)+0x1000+4   # rva of target if disp at i ends insn
def xrefs(va,extra=(0,)):
    r=va-BASE; out=[]
    for e in extra:
        idx=np.nonzero(tgt==r - e)[0] if e==0 else np.nonzero(tgt+e==r)[0]
        out+= [BASE+0x1000+int(i) for i in idx]
    return out   # va of disp field
md=Cs(CS_ARCH_X86,CS_MODE_64); md.detail=False
def dis(va,n=40,back=0):
    o=va2off(va)
    for i in md.disasm(d[o:o+n*15],va):
        print('%x: %-8s %s'%(i.address,i.mnemonic,i.op_str)); n-=1
        if n<=0: break
def func(va):
    o=va2off(va)
    j=d.rfind(b'\xcc\xcc',0,o)
    return (off2va(j+2),)
def callers(va):
    r=va-BASE
    idx=np.nonzero(tgt==r)[0]
    out=[]
    for i in idx:
        if code[i-1] in (0xE8,0xE9): out.append(BASE+0x1000+int(i)-1)
    return out
