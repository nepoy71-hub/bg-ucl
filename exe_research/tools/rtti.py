from lib import *
def vtables(name):
    # name like b'.?AVThinkUnitSetPlay@bp@ai@match@@'
    i=d.find(name); 
    if i<0: return []
    td=off2va(i-0x10)          # type descriptor start (vfptr, spare, name)
    rva=td-BASE
    out=[]
    # RTTI complete object locator: signature(1), offset, cdOffset, pTypeDescriptor(rva), pClassHierarchy(rva), pSelf(rva)
    pat=struct.pack('<I',rva)
    for m in re.finditer(re.escape(pat),d):
        o=m.start()-12
        if o<0: continue
        sig=struct.unpack_from('<I',d,o)[0]
        if sig!=1: continue
        selfrva=struct.unpack_from('<I',d,o+20)[0]
        if off2va(o) is None or selfrva!=off2va(o)-BASE: continue
        col=off2va(o)
        # vtable: pointer to COL sits right before vtable
        for q in re.finditer(re.escape(struct.pack('<Q',col)),d):
            vt=off2va(q.start()+8)
            fns=[]
            k=q.start()+8
            while True:
                f=struct.unpack_from('<Q',d,k)[0]
                if not (0x140001000<=f<0x14252e800): break
                fns.append(f); k+=8
            out.append((vt,struct.unpack_from('<I',d,o+4)[0],fns))
    return out
if __name__=='__main__':
    import sys
    for nm in sys.argv[1:]:
        for vt,off,fns in vtables(nm.encode()):
            print(nm,'vtable',hex(vt),'offset',off,'n',len(fns)); print('  ',' '.join(hex(f) for f in fns[:24]))
