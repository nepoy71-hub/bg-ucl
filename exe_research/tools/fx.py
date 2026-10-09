from plib import *
def fstart(addr,maxback=0x4000):
    a=addr&~0xf
    while a>addr-maxback:
        o=va2off(a)
        if d[o-1] in (0xcc,0xc3) or d[o-5]==0xe9:
            ok=False
            for i in md.disasm(d[o:o+(addr-a)+16],a):
                if i.address==addr: ok=True;break
                if i.address>addr or i.mnemonic=='int3': break
            if ok: return a
        a-=16
    return None
def dump(f,maxb=0x10000,save=True):
    out=[]; end=f
    # follow until int3 after having passed all forward jump targets
    far=f
    for i in md.disasm(pget(f,maxb),f):
        if i.mnemonic=='int3' and i.address>far: break
        out.append('%x: %-8s %s'%(i.address,i.mnemonic,i.op_str))
        if i.mnemonic.startswith('j') and i.op_str.startswith('0x'):
            t=int(i.op_str,16)
            if f<t<f+maxb and t>far and i.mnemonic!='jmp': far=t
            elif i.mnemonic=='jmp' and f<t<f+0x3000 and t>far: far=t
    if save: open('fkw/%x.txt'%f,'w').write('\n'.join(out))
    return out
