# NeuroPyxels: loading, processing and plotting Neuropixels data in python

[![PyPI Version](https://img.shields.io/pypi/v/npyx.svg)](https://pypi.org/project/npyx/)

NeuroPyxels (npyx) is a python library built for electrophysiologists using Neuropixels electrodes. It features a suite of core utility functions for loading, processing and plotting Neuropixels data.

This package results from the needs of an experimentalist who could not stand MATLAB, hence wrote himself a suite of functions to emotionally bear with doing neuroscience. There isn't any dedicated preprint available yet, so if you enjoy this package and use it for your research, please star [the github repo](https://github.com/m-beau/NeuroPyxels) (click on the top-right star button!) and cite [this paper](https://www.nature.com/articles/s41593-019-0381-8). Cheers!

There isn't any better doc atm - post an issue if you have any question, or email [Maxime Beau](maximebeaujeanroch047@gmail.com) (PhD Hausser lab, UCL). You can also use the [Neuropixels slack workgroup](neuropixelsgroup.slack.com), channel #NeuroPyxels.

## Documentation:
Npyx works in harmony with the data formatting employed by [SpikeGLX](https://billkarsh.github.io/SpikeGLX/) used in combination with [Kilosort](https://github.com/MouseLand/Kilosort) and [Phy](https://phy.readthedocs.io/en/latest/).

<ins>Npyx is fast because it never computes the same thing twice</ins> - in the background, it saves most relevant outputs (spike trains, waveforms, correlograms...) at **kilosort_dataset/npyxMemory**, from where they are simply reloaded if called again. An important parameter controlling this behaviour is **`again`** (boolean), by default set to False: if True, the function will recompute the output rather than loading it from npyxMemory. This is important to be aware of this behaviour, as it can lead to mind boggling bugs. For instance, if you load the train of unit then re-spikesort your dataset, e.g. you split unit 56 in 504 and 505, the train of the old unit 56 will still exist at kilosort_dataset/npyxMemory and you will be able to load it even though the unit is gone!

Most npyx functions take at least one input: **`dp`**, which is the path to your Kilosort-phy dataset. You can find a [full description of the structure of such datasets](https://phy.readthedocs.io/en/latest/sorting_user_guide/#installation) on phy documentation.

Other typical parameters are: **`verbose`** (whether to print a bunch of informative messages, useful when debugging), **`saveFig`** (boolean) and **`saveDir`** (whether to save the figure in saveDir for plotting functions).

Importantly, **`dp`** can also be the path to a merged dataset, generated with `npyx.merge_datasets()` - <ins>every function will run as smoothly on merged datasets as on any regular dataset</ins>. See below for more details.

More precisely, every function requires the files `myrecording.ap.meta`, `spike_times.npy` and `spike_clusters.npy`. If you have started spike sorting, `cluter_groups.tsv` will also be required obviously (will be created filled with 'unsorted' groups if none is found). Then particular functions will require particular files: loading waveforms with `npyx.spk_wvf.wvf` or extracting your sync channel with `npyx.io.get_npix_sync` require the raw data `myrecording.ap.bin`, `npyx.spk_wvf.templates` the files `templates.npy` and `spike_templates.npy`, and so on. This allows you to only transfer the strictly necassary files for your use case from a machine to the next: for instance, if you only want to make behavioural analysis of spike trains but do not care about the waveforms, you can run `get_npix_sync` on a first machine (which will generate a `sync_chan` folder containing extracted onsets/offsets from the sync channel(s)), then excklusively transfer the `sync_chan` folder along with `spike_times.npy` and `spike_clusters.npy` (all very light files) on another computer and analyze your data there seemlessly.

Example use cases are:
### Load synchronization channel
```python
from npyx.io import get_npix_sync
dp = 'datapath/to/kilosort_dataset'
onsets, offsets = get_npix_sync(dp)
# onsets/offsets are dictionnaries
# whose keys are ids of sync channel where signal was detected,
# and values the times of up (onsets) or down (offsets) threshold crosses in seconds.
```
### Get good units from dataset
```python
from npyx.gl import get_units
units = get_units(dp, quality='good')
```
### Load spike times from unit u
```python
from npyx.spk_t import trn
u=234
t = trn(dp, u) # gets all spikes from unit 234, in samples
```

### Load waveforms from unit u
```python
from npyx.io import read_spikeglx_meta
from npyx.spk_t import ids, trn
from npyx.spk_wvf import get_peak_chan, wvf, templates

# returns a random sample of 100 waveforms from unit 234, in uV, across 384 channels
waveforms = wvf(dp, u) # return array of shape (n_waves, n_samples, n_channels)=(100, 82, 384) by default
waveforms = wvf(dp, u, n_waveforms=1000, t_waveforms=90) # now 1000 random waveforms, 90 samples=3ms long
waveforms = wvf(dp, u, periods=[(0,100),(300,400)]) # now all waveforms occurring between 0-100s and 300-400s
u_ids = npyx.spk_t.ids(dp,u) # get ids of unit u: all spikes have a unique index in the dataset, which is their rank sorted by time (as in spike_times.npy)
waveforms = wvf(dp, u, spike_ids=u_ids[:10]) # the 10 first waveforms of u

# Get the unit peak channel (channel with the biggest amplitude)
peak_chan = get_peak_chan(dp,u)
# extract the waveforms located on peak channel
w=waves[:,:,peak_chan]

# Extract waveforms of spikes occurring between
# 900 and 1000s in the recording, because that's when your mouse scratched its butt
fs=read_spikeglx_meta['sRateHz']
t=trn(dp,u)/fs # convert in s
ids=ids(dp,u)[(t>900)&(t<1000)]
waves = wvf(dp, u, spike_ids=ids)

# If you want to load the templates instead (lighter)
temp = templates(dp,u) # return array of shape (n_templates, 82, n_channels)
```

### Compute auto/crosscorrelogram between 2 units
```python
from npyx.corr import ccg
dp = 'path/to/dataset'
# returns ccg between 234 and 92 with a binsize of 0.2 and a window of 80
c = ccg(dp, [234,92], cbin=0.2, cwin=80)
```

### Plot correlograms and waveforms from unit u
```python
# all plotting functions return matplotlib figures
from npyx.plot import plot_wvf, get_peak_chan
dp = 'path/to/dataset'
u=234
# plot waveform, 2.8ms around templates center, on 16 channels around peak channel
# (the peak channel is found automatically, no need to worry about finding it)
fig = plot_wvf(dp, u, Nchannels=16, t_waveforms=2.8)

# But if you wished to get it, simply run
peakchannel = get_peak_chan(dp, u)
```
<img src="https://raw.githubusercontent.com/m-beau/NeuroPyxels/master/images/wvf.png" width="200"/>

```python
# plot ccg between 234 and 92
fig = plot_ccg(dp, [u,92], cbin=0.2, cwin=80, as_grid=True)
```
<img src="https://raw.githubusercontent.com/m-beau/NeuroPyxels/master/images/ccg.png" width="400"/>


### Plot chunk of raw data with overlaid units
```python
units = [1,2,3,4,5,6]
channels = np.arange(70,250)
# raw data are whitened, high-pass filtered and median-subtracted by default - parameters are explicit below
plot_raw_units(dp, times=[0,0.130], units = units, channels = channels,
               colors=['orange', 'red', 'limegreen', 'darkgreen', 'cyan', 'navy'],
               lw=1.5, offset=450, figsize=(6,16), Nchan_plot=10,
               med_sub=1, whiten=1, hpfilt=1)
```
<img src="https://raw.githubusercontent.com/m-beau/NeuroPyxels/master/images/raw.png" width="400"/>

### Merge datasets acquired on two probes simultaneously
```python
# The three recordings need to include the same sync channel.
from npyx.merger import merge_datasets
dps = ['same_folder/lateralprobe_dataset',
       'same_folder/medialprobe_dataset',
       'same_folder/anteriorprobe_dataset']
probenames = ['lateral','medial','anterior']
dp_dict = {p:dp for p, dp in zip(dps, probenames)}

# This will merge the 3 datasets (only relevant information, not the raw data) in a new folder at
# dp_merged: same_folder/merged_lateralprobe_dataset_medialprobe_dataset_anteriorprobe_dataset
# where all npyx functions can smoothly run.
# The only difference is that units now need to be called as floats,
# of format u.x (u=unit id, x=dataset id [0-2]).
# lateralprobe, medial probe and anteriorprobe x will be respectively 0,1 and 2.
dp_merged, datasets_table = merge_datasets(dp_dic)


--- Merged data (from 2 dataset(s)) will be saved here: /same_folder/merged_lateralprobe_dataset_medialprobe_dataset_anteriorprobe_dataset.

--- Loading spike trains of 2 datasets...

sync channel extraction directory found: /same_folder/lateralprobe_dataset/sync_chan
Data found on sync channels:
chan 2 (201 events).
chan 4 (16 events).
chan 5 (175 events).
chan 6 (28447 events).
chan 7 (93609 events).
Which channel shall be used to synchronize probes? >>> 7

sync channel extraction directory found: /same_folder/medialprobe_dataset/sync_chan
Data found on sync channels:
chan 2 (201 events).
chan 4 (16 events).
chan 5 (175 events).
chan 6 (28447 events).
chan 7 (93609 events).
Which channel shall be used to synchronize probes? >>> 7

sync channel extraction directory found: /same_folder/anteriorprobe_dataset/sync_chan
Data found on sync channels:
chan 2 (201 events).
chan 4 (16 events).
chan 5 (175 events).
chan 6 (28194 events).
chan 7 (93609 events).
Which channel shall be used to synchronize probes? >>> 7

--- Aligning spike trains of 2 datasets...
More than 50 sync signals found - for performance reasons, sub-sampling to 50 homogenoeously spaced sync signals to align data.
50 sync events used for alignement - start-end drift of -3080.633ms

--- Merged spike_times and spike_clusters saved at /same_folder/merged_lateralprobe_dataset_medialprobe_dataset_anteriorprobe_dataset.

--> Merge successful! Use a float u.x in any npyx function to call unit u from dataset x:
- u.0 for dataset lateralprobe_dataset,
- u.1 for dataset medialprobe_dataset,
- u.2 for dataset anteriorprobe_dataset.


t = trn(dp_merged, 92.1) # get spikes of unit 92 in dataset 1 i.e. medialprobe
fig=plot_ccg(dp_merged,[10.0, 92.1, cbin=0.2, cwin=80]) # compute CCG between 2 units across datasets
```


<br/>

## Installation:

Using a conda environment is very much advised. Instructions here: [manage conda environments](https://docs.conda.io/projects/conda/en/latest/user-guide/tasks/manage-environments.html)

Npyx supports Python 3.7+.

- as a user
  - from pip (normally up to date)
  ```bash
  conda create -n my_env python=3.7
  conda activate my_env
  pip install npyx
  python -c 'import npyx' # should not return any error
  # If it does, install any missing dependencies with pip (hopefully none!)
  ```
  - from the remote repository (always up to date - still private at time of writing, pip is a prerelease)
  ```bash
  conda activate env_name
  pip install git+https://github.com/Npix-routines/NeuroPyxels@master
  ```
- as a superuser (recommended if plans to work on it/regularly pull upgrades)
  > Tip: in an ipython/jupyter session, use `%load_ext autoreload` then `%autoreload` to make your local edits active in your session without having to restart your kernel. Amazing for development.
    ```bash
    conda activate my_env
    cd path/to/save_dir # any directory where your code will be accessible by your editor and safe. NOT downloads folder.
    git clone https://github.com/Npix-routines/NeuroPyxels
    cd NeuroPyxels
    python setup.py develop # this will create an egg link to save_dir, which means that you do not need to reinstall the package each time you pull an udpate from github.
    ```
    and pull every now and then:
    ```bash
    conda activate env_name
    cd path/to/save_dir/NeuroPyxels
    git pull
    # And that's it, thanks to the egg link no need to reinstall the package!
    ```
<br/>

## Developer cheatsheet

Useful link to [create a python package from a git repository](https://towardsdatascience.com/build-your-first-open-source-python-project-53471c9942a7)


### Push local updates to github:
```bash
# ONLY ON DEDICATED BRANCH

cd path/to/save_dir/NeuroPyxels
git checkout DEDICATED_BRANCH_NAME # ++++++ IMPORTANT
git add.
git commit -m "commit details - try to be specific"
git push origin DEDICATED_BRANCH_NAME # ++++++ IMPORTANT

# Then pull request to master branch using the online github green button! Do not forget this last step, to allow the others repo to sync.
```

### Push local updates to PyPI (Maxime)
First change the version in ./setup.py in a text editor
```python
setup(name='npyx',
      version='1.0',... # change to 1.1, 1.1.1...
```
Then delete the old distribution files before re-generating them for the new version using twine:
```bash
rm -r ./dist
rm -r ./build
rm -r ./npyx.egg-info
python setup.py sdist bdist_wheel # this will generate version 1.1 wheel without overwriting version 1.0 wheel in ./dist
```
Before pushing them to PyPI (older versions are saved online!)
```bash
twine upload dist/*

Uploading distributions to https://upload.pypi.org/legacy/
Enter your username: your-username
Enter your password: ****
Uploading npyx-1.1-py3-none-any.whl
100%|████████████████████████████████████████████████████████| 156k/156k [00:01<00:00, 96.8kB/s]
Uploading npyx-1.1.tar.gz
100%|█████████████████████████████████████████████████████████| 150k/150k [00:01<00:00, 142kB/s]

```
