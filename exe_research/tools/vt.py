from fx import *
RD0=0x252de00; RDN=0xe6bc00
rd=np.frombuffer(d,dtype='<u8',count=RDN//8,offset=RD0)
def rtti_name(vt):
    try:
        col=struct.unpack('<Q',pget(vt-8,8))[0]
        if not (0x142530000<=col<0x1433a0000): return None
        sig=struct.unpack('<I',pget(col,4))[0]
        if sig!=1: return None
        td=BASE+struct.unpack('<I',pget(col+12,4))[0]
        o=va2off(td+0x10); s=d[o:d.find(b'\0',o)]
        return s.decode() if s.startswith(b'.?A') else None
    except Exception: return None
def owners(f):
    out=[]
    for i in np.nonzero(rd==f)[0]:
        va=off2va(RD0+int(i)*8)
        # walk back to vtable start
        a=va
        for k in range(0,200):
            n=rtti_name(a)
            if n: out.append((n,a,(va-a)//8)); break
            a-=8
    return out
if __name__=='__main__':
    import sys
    for x in sys.argv[1:]:
        f=int(x,16); print(hex(f),owners(f))
