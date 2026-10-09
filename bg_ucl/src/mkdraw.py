import random, sys
random.seed(int(sys.argv[1]) if len(sys.argv)>1 else 1)
N=36
def edges():
    E=[]
    for p in range(4):                       # own pot: directed cycle, i hosts i+1
        for i in range(9): E.append((p*9+i, p*9+(i+1)%9))
    for p in range(4):
        for q in range(p+1,4):
            a=random.randrange(9); b=random.randrange(9)
            while (a+b)%9==0: b=random.randrange(9)   # the two opponents must differ
            for i in range(9):
                E.append((p*9+i, q*9+(i+a)%9))       # P_i at home to Q_{i+a}
                E.append((q*9+i, p*9+(i+b)%9))       # Q_i at home to P_{i+b}
    return E
import networkx as nx
def rounds(E):
    for t in range(300):
        left=set(E); col={}
        ok=True
        for r in range(8):
            G=nx.Graph()
            for (h,a) in left: G.add_edge(h,a,weight=1+random.random())
            M=nx.max_weight_matching(G,maxcardinality=True)
            if len(M)!=18: ok=False;break
            for u,v in M:
                e=(u,v) if (u,v) in left else (v,u)
                col[e]=r; left.discard(e)
        if ok: return col
    return None
for attempt in range(200):
    E=edges()
    assert len(E)==144 and len(set(frozenset(e) for e in E))==144
    col=rounds(E)
    if col: break
else: sys.exit("no colouring")
# checks
for v in range(N):
    per={p:[0,0] for p in range(4)}
    for h,a in E:
        if h==v: per[a//9][0]+=1
        if a==v: per[h//9][1]+=1
    assert all(per[p]==[1,1] for p in range(4)), (v,per)
    assert sorted(col[e] for e in E if v in e)==list(range(8))
rows=[]
for r in range(8):
    ms=[e for e in E if col[e]==r]; assert len(ms)==18
    random.shuffle(ms)
    for k,(h,a) in enumerate(ms): rows.append((2*r+(k>=9),h,a))
rows.sort()
out=["/* league phase draw: 36 clubs, pot = list position / 9. Every club plays 8 different",
" * opponents, two from every pot (its own included), one of them at home and one away.",
" * Each round is a perfect matching of the 36, split over two matchdays of nine. */",
"typedef struct { unsigned char md, home, away; } fl26_pair_t;",
"#define FL26_SWISS36_CLUBS      36","#define FL26_SWISS36_PAIRS      144","#define FL26_SWISS36_MATCHDAYS  16",
"static const fl26_pair_t FL26_SWISS36[FL26_SWISS36_PAIRS] = {"]
line=[]
for i,(m,h,a) in enumerate(rows):
    line.append("{%2d,%2d,%2d}"%(m,h,a))
    if len(line)==6: out.append("  "+", ".join(line)+","); line=[]
out.append("};")
open("../swiss_table.h","w").write("\n".join(out)+"\n")
print("ok, attempt",attempt)
