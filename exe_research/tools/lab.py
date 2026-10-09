import csv,struct,sys
rows=list(csv.DictReader(open('/mnt/user-data/uploads/Claude outputs/F4L_Gameplay_Editor_v1.0/data/field_labels_latest.csv',encoding='utf-8-sig',errors='replace')))
def obj(binf,name):
    u=open(binf+'.unz','rb').read(); n=struct.unpack_from('<I',u,0)[0]
    for i in range(n):
        o,s,no=struct.unpack_from('<III',u,8+i*12)
        if u[no:u.find(b'\0',no)].decode()==name: return u[o:o+s]
def show(binf,name):
    b=obj(binf,name); print('=====',binf,name,len(b))
    for r in rows:
        if r['file']==binf and r['object']==name:
            off=int(r['offset_hex'],16); t=r['type']; st=r['storage']
            try:
                if t=='float': v='%.4g'%struct.unpack_from('<f',b,off)[0]
                elif st=='byte' or t=='bool': v=b[off]
                elif t in('int','uint','int32','uint32'): v=struct.unpack_from('<i',b,off)[0]
                else: v='%s/%s:%s'%(t,st,b[off:off+8].hex())
            except Exception as e: v='?'
            print('  %-6s %-44s %-10s %s'%(r['offset_hex'],r['label'],v,(r['notes'] or '')[:90]))
if __name__=='__main__':
    for a in sys.argv[1:]:
        f,o=a.split(':'); show(f,o)
