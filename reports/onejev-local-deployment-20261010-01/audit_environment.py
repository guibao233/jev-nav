import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import subprocess

root=Path('/data/guiyuanze/share/guiyuanze/code/habitat-gs/jev_nav').resolve()
deploy=root/'local_models/onejev-4b'
manifest=json.loads((deploy/'deployment.json').read_text())
assert subprocess.check_output(['git','-C',str(deploy/'source'),'rev-parse','HEAD'],text=True).strip()==manifest['qev_commit']
assert not subprocess.check_output(['git','-C',str(deploy/'source'),'status','--porcelain'],text=True).strip()
assert hashlib.sha256((deploy/'requirements.lock.txt').read_bytes()).hexdigest()==manifest['requirements_lock_sha256']
for name, version in manifest['packages'].items():
    assert metadata.version(name)==version
import qev
package=Path(qev.__file__).resolve().parent
for name, expected in manifest['qev_package_files'].items():
    assert hashlib.sha256((package/name).read_bytes()).hexdigest()==expected
upstream=json.loads((deploy/'upstream-files.json').read_text())
assert upstream['sha']==manifest['model_revision']
file_checks=[]
for entry in upstream['siblings']:
    path=deploy/'weights'/entry['rfilename']
    if not path.is_file() or entry.get('lfs'):
        continue
    data=path.read_bytes()
    blob=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
    assert blob==entry['blobId']
    file_checks.append({'file':entry['rfilename'],'git_blob_sha1':blob,'sha256':hashlib.sha256(data).hexdigest()})
import torch
import transformers
assert hasattr(transformers,'Qwen3_5ForConditionalGeneration')
assert not torch.cuda.is_initialized()
receipt={'status':'passed','gpu_initialized':False,'source_clean':True,'qev_commit':manifest['qev_commit'],
    'locked_packages_checked':len(manifest['packages']),'qev_source_files_checked':len(manifest['qev_package_files']),
    'python':manifest['python_version'],'torch':torch.__version__,'torch_cuda_runtime':torch.version.cuda,
    'transformers':transformers.__version__,'qev':qev.__version__,'pip_check':'No broken requirements found.',
    'requirements_lock_sha256':manifest['requirements_lock_sha256'],'official_small_files_checked':file_checks,
    'note':'CPU import/provenance only; CUDA availability, model loading and forward execution not checked.'}
(root/'reports/onejev-local-deployment-20261010-01/environment-validation.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt,indent=2))
