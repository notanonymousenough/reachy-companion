from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import json,math,urllib.request,hashlib
import argparse
parser=argparse.ArgumentParser(description='Regenerate the adapted official emotion asset from pinned source data')
parser.add_argument('--cache', type=Path, default=Path('data/emotion-source'))
parser.add_argument('--output', type=Path, default=Path('src/reachy_companion/assets/pollen-emotions-v1.json'))
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
settings=json.loads((root/'profiles/friend.json').read_text())['conversation']['expressions']['library']
revision=settings['revision'];mapping=settings['emotions'];phases=settings['phases']
names=sorted({n for group in list(mapping.values())+list(phases.values()) for n in group})
def get(name):
 url=f'https://huggingface.co/datasets/pollen-robotics/reachy-mini-emotions-library/resolve/{revision}/{name}.json'
 cache=args.cache/revision/(name+'.json');cache.parent.mkdir(parents=True,exist_ok=True)
 if not cache.exists():cache.write_bytes(urllib.request.urlopen(url,timeout=40).read())
 raw=cache.read_bytes();data=json.loads(raw);source=data['set_target_data'];times=data['time']
 frames=[]
 for i in range(24):
  j=round(i*(len(source)-1)/23);p=source[j];r=p['head']
  angles=[math.atan2(r[2][1],r[2][2]),math.asin(max(-1,min(1,-r[2][0]))),math.atan2(r[1][0],r[0][0])]
  frames.append([math.degrees(a) for a in angles]+[math.degrees(a) for a in p['antennas']])
 head_scale=min(1,10/max(1,max(abs(v) for f in frames for v in f[:3])))
 ear_scale=min(1,24/max(1,max(abs(v) for f in frames for v in f[3:])))
 frames=[[round(v*(head_scale if j<3 else ear_scale),3) for j,v in enumerate(f)] for f in frames]
 return name,{'duration':round(times[-1]-times[0],3),'frames':frames,'sha256':hashlib.sha256(raw).hexdigest()}
with ThreadPoolExecutor(max_workers=4) as pool:clips=dict(pool.map(get,names))
asset={'source':'pollen-robotics/reachy-mini-emotions-library','revision':revision,'license':'Apache-2.0','modifications':'24 sampled orientation/antenna keyframes per clip; normalized to 10/24 degrees; translations/body/sounds removed.','clips':clips}
args.output.parent.mkdir(parents=True,exist_ok=True)
args.output.write_text(json.dumps(asset,separators=(',',':'))+'\n')
print('Converted',len(clips),'official clips for',len(mapping),'emotions')
