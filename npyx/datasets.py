import copy
import pickle

import h5py
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from tqdm.auto import tqdm

import npyx

CENTRAL_RANGE = 60

N_CHANNELS = 10

LABELLING = {
    "PkC_cs": 5,
    "PkC_ss": 4,
    "MFB": 3,
    "MLI": 2,
    "GoC": 1,
    "GrC": 0,
    "unlabelled": -1,
}

# To do the inverse
CORRESPONDENCE = {
    5: "PkC_cs",
    4: "PkC_ss",
    3: "MFB",
    2: "MLI",
    1: "GoC",
    0: "GrC",
    -1: "unlabelled",
}

# pylint: disable=no-member


def save(file_name, obj):
    with open(file_name, "wb") as fobj:
        pickle.dump(obj, fobj)


def load(file_name):
    with open(file_name, "rb") as fobj:
        return pickle.load(fobj)


def get_neuron_attr(hdf5_file_path, id=None, file=None):
    """
    Prompts the user to select a given neuron's file to load.
    Otherwise, can specify which neuron's id and which file we want to load directly
    """
    neuron_ids = []
    with h5py.File(hdf5_file_path, "r") as hdf5_file:
        for name in hdf5_file:
            if "neuron" not in name:
                continue
            pi = name.split("_")[0]
            neuron_id = name.split("_")[-1]
            neuron_ids.append(neuron_id)
        if id is None:
            neuron_ids = [int(neuron_id) for neuron_id in neuron_ids]
            first_input = input(f"Select a neuron id from: {neuron_ids}")
            if first_input == "":
                print("No neuron id selected, exiting")
                return None
            first_path = f"{str(pi)}_neuron_{str(first_input)}"

            second_input = input(
                f"Select a file to load from: {ls(hdf5_file[first_path])}"
            )
            if second_input == "":
                print("No attribute selected, exiting")
                return None
            second_path = first_path + "/" + str(second_input)

            return hdf5_file[second_path][(...)]
        else:
            return_path = f"{str(pi)}_neuron_{str(id)}/{str(file)}"
            return hdf5_file[return_path][(...)]


def ls(hdf5_file_path):
    """
    Given an hdf5 file path or an open hdf5 file python object, returns the child directories.
    """
    if type(hdf5_file_path) is not str:
        return list(hdf5_file_path.keys())
    with h5py.File(hdf5_file_path, "r") as hdf5_file:
        return list(hdf5_file.keys())


def normalise_wf(wf):
    """
    Custom normalisation so that the through of the waveform is set to -1
    or the peak is set to +1 if the waveform is dendritic
    """
    baseline = wf[:, :20].mean(axis=1, keepdims=True)
    through = wf.min()
    peak = wf.max()
    return (
        (wf - baseline) / np.abs(through)
        if np.abs(through) > np.abs(peak)
        else (wf - baseline) / np.abs(peak)
    )


def crop_original_wave(waveform, central_range=60, n_channels=10):
    """
    It takes a waveform of shape (n_channels, central_range), and returns a copy of the waveform with the central 60 samples in the horizontal
    direction, and the central 10 channels in the vertical direction

    Args:
      waveform: the waveform to be preprocessed
      central_range: the number of samples to take from the centre of the waveform. Defaults to 60
      n_channels: The number of channels to use around the peak. Defaults to 10

    Returns:
      The waveform cropped to the central range and the number of channels specified.
    """
    # First argsort to find the peak channels
    # Then if the absolute max amplitude channel is "too close to the edge", find the second max and so on.
    # If the peak channel is in the middle, then just take the central 10 channels
    centre = waveform.shape[1] // 2
    if waveform.shape[0] <= n_channels:
        return waveform[
            :, (centre - central_range // 2) : (centre + central_range // 2)
        ]

    channels_by_amplitude = np.argsort(np.max(np.abs(waveform), axis=1))

    cropped_wvf = np.array([0])
    i = 1
    while cropped_wvf.shape[0] < n_channels and i < waveform.shape[0]:
        peak_channel = channels_by_amplitude[-i]
        cropped_wvf = waveform[
            (peak_channel - n_channels // 2) : (peak_channel + n_channels // 2),
            (centre - central_range // 2) : (centre + central_range // 2),
        ].copy()
        i += 1

    return cropped_wvf


def resample_acg(acg, window_size=20, keep_same_size=True):
    """
    Given an ACG, add artificial points to it.
    If keep_same_size is True, the ACG will be of the same size: this is achieved
    by undersapling points at the end of the ACG.
    """
    y = np.array(acg).copy()
    X = np.linspace(0, len(y), len(y))

    interpolated_window = y[:window_size]
    # Create interpolating points
    avg_arr = (interpolated_window + np.roll(interpolated_window, -1)) / 2.0
    avg_enhanced = np.vstack([interpolated_window, avg_arr]).flatten("F")[:-1]

    # Create new_y enhanced with interpolating points
    new_y = np.concatenate((avg_enhanced.ravel(), y[window_size:].ravel()), axis=0)

    if keep_same_size == False:
        return new_y

    # Select final points to remove
    idxes = np.ones_like(new_y).astype(bool)
    idxes[-2 * window_size :: 2] = False

    return new_y[idxes]


class NeuronsDataset:
    """
    Custom class for the cerebellum dataset, containing all information about the labelled and unlabelled neurons.
    """

    def __init__(
        self,
        dataset,
        quality_check=True,
        normalise_wvf=False,
        normalise_acg=False,
        resample_acgs=True,
        cut_acg=True,
        central_range=CENTRAL_RANGE,
        n_channels=N_CHANNELS,
        reshape_fortran_to_c=False,
        _label="optotagged_label",
        _labelling=LABELLING,
        _use_amplitudes=False,
    ):

        # Store useful metadata about how the dataset was extracted
        self._n_channels = n_channels
        self._central_range = central_range

        # Initialise empty lists to extract data
        self.wf_list = []
        self.acg_list = []
        self.spikes_list = []
        self.labels_list = []
        self.info = []

        if _use_amplitudes:
            self.amplitudes_list = []

        neuron_ids = []
        with h5py.File(dataset, "r") as hdf5_file:
            for name in hdf5_file:
                if "neuron" in name:
                    neuron_id = name.split("_")[-1]
                    neuron_ids.append(int(neuron_id))

        discarded_df = pd.DataFrame(columns=["neuron_id", "label", "dataset", "reason"])
        for wf_n in tqdm(np.sort(neuron_ids), desc="Reading dataset", leave=False):
            try:
                # Get the label for this wvf
                label = get_neuron_attr(dataset, wf_n, _label).ravel()[0]

                # If the neuron is labelled we extract it anyways
                if label != 0 and not isinstance(label, (np.ndarray, np.int64)):
                    label = str(label.decode("utf-8"))
                    self.labels_list.append(label)

                elif label != 0:
                    label = label.item()
                    self.labels_list.append(label)
                else:
                    self.labels_list.append("unlabelled")

                spike_idxes = get_neuron_attr(dataset, wf_n, "spike_indices")

                if quality_check:
                    sane_spikes = get_neuron_attr(dataset, wf_n, "sane_spikes")
                    fn_fp_spikes = get_neuron_attr(
                        dataset, wf_n, "fn_fp_filtered_spikes"
                    )
                    mask = fn_fp_spikes & sane_spikes
                    spikes = spike_idxes[mask].copy()
                else:
                    spikes = spike_idxes

                # if spikes is void after quality checks, skip this neuron
                if len(spikes) == 0:
                    dataset_name = (
                        get_neuron_attr(dataset, wf_n, "dataset_id")
                        .ravel()[0]
                        .decode("utf-8")
                    )
                    discarded_df = pd.concat(
                        (
                            discarded_df,
                            pd.DataFrame(
                                {
                                    "neuron_id": [
                                        get_neuron_attr(
                                            dataset, wf_n, "neuron_id"
                                        ).ravel()[0]
                                    ],
                                    "label": [label],
                                    "dataset": [dataset_name],
                                    "reason": ["quality checks"],
                                }
                            ),
                        ),
                        ignore_index=True,
                    )
                    del self.labels_list[-1]
                    continue

                # Extract amplitudes if requested
                if _use_amplitudes:
                    amplitudes = get_neuron_attr(dataset, wf_n, "amplitudes")
                    self.amplitudes_list.append(amplitudes)

                # Extract waveform using provided parameters
                wf = get_neuron_attr(dataset, wf_n, "mean_waveform_preprocessed")

                if reshape_fortran_to_c:
                    wf = wf.reshape(list(wf.shape)[::-1])

                # Make sure if we need to transpose the waveform or not
                if wf.shape[0] > wf.shape[1]:
                    wf = wf.T

                # Also, if the waveform is 1D (i.e. only one channel), we need to tile it to make it 2D.
                # Alternatively, if it is not spread on enough channels, we want to tile the remaining
                if wf.squeeze().ndim == 1:
                    wf = np.tile(wf, (n_channels, 1))

                if wf.shape[0] < n_channels:
                    repeats = [wf[0][None, :]] * (n_channels - wf.shape[0])
                    wf = np.concatenate((*repeats, wf), axis=0)

                if normalise_wvf:
                    self.wf_list.append(
                        crop_original_wave(normalise_wf(wf), central_range, n_channels)
                        .ravel()
                        .astype(float)
                    )
                else:
                    self.wf_list.append(
                        crop_original_wave(wf, central_range, n_channels)
                        .ravel()
                        .astype(float)
                    )
                if self.wf_list[-1].shape[0] != n_channels * central_range:
                    dataset_name = (
                        get_neuron_attr(dataset, wf_n, "dataset_id")
                        .ravel()[0]
                        .decode("utf-8")
                    )
                    discarded_df = pd.concat(
                        (
                            discarded_df,
                            pd.DataFrame(
                                {
                                    "neuron_id": [
                                        get_neuron_attr(
                                            dataset, wf_n, "neuron_id"
                                        ).ravel()[0]
                                    ],
                                    "label": [label],
                                    "dataset": [dataset_name],
                                    "reason": ["shape mismatch"],
                                }
                            ),
                        ),
                        ignore_index=True,
                    )
                    del self.labels_list[-1]
                    del self.wf_list[-1]
                    if hasattr(self, "amplitudes_list"):
                        del self.amplitudes_list[-1]
                    continue

                if normalise_acg:
                    acg = npyx.corr.acg("hello", 4, 1, 200, train=spikes)
                    normal_acg = np.clip(acg / np.max(acg), 0, 10)
                    self.acg_list.append(normal_acg.astype(float))
                else:
                    acg = npyx.corr.acg("hello", 4, 1, 200, train=spikes)
                    self.acg_list.append(acg.astype(float))
                self.spikes_list.append(spikes.astype(int))
                # Extract useful metadata
                dataset_name = (
                    get_neuron_attr(dataset, wf_n, "dataset_id")
                    .ravel()[0]
                    .decode("utf-8")
                )
                neuron_id = get_neuron_attr(dataset, wf_n, "neuron_id").ravel()[0]
                if not isinstance(neuron_id, (np.ndarray, np.int64, int)):
                    neuron_id = neuron_id.decode("utf-8")
                neuron_metadata = dataset_name + "/" + str(neuron_id)
                self.info.append(str(neuron_metadata))

            except KeyError:
                dataset_name = (
                    get_neuron_attr(dataset, wf_n, "dataset_id")
                    .ravel()[0]
                    .decode("utf-8")
                )
                discarded_df = pd.concat(
                    (
                        discarded_df,
                        pd.DataFrame(
                            {
                                "neuron_id": [
                                    get_neuron_attr(dataset, wf_n, "neuron_id").ravel()[
                                        0
                                    ]
                                ],
                                "label": [label],
                                "dataset": [dataset_name],
                                "reason": ["KeyError"],
                            }
                        ),
                    ),
                    ignore_index=True,
                )
                continue

        self.discarded_df = discarded_df
        if cut_acg:
            acg_list_cut = [x[len(x) // 2 :] for x in self.acg_list]
        else:
            acg_list_cut = self.acg_list
        if resample_acgs:
            acg_list_resampled = list(map(resample_acg, acg_list_cut))
        else:
            acg_list_resampled = acg_list_cut

        self.targets = np.array(
            (pd.Series(self.labels_list).replace(_labelling).values)
        )
        self.wf = np.stack(self.wf_list, axis=0)
        self.acg = np.stack(acg_list_resampled, axis=0)

        print(
            f"{len(self.wf_list)} neurons loaded, of which labelled: {sum(self.targets != -1)} \n"
            f"{len(discarded_df)} neurons discarded, of which labelled: {len(discarded_df[discarded_df.label != 0])}. More details at the 'discarded_df' attribute."
        )

    def make_labels_only(self):
        """
        It removes all the data points that have no labels
        """
        mask = self.targets != -1
        self.wf = self.wf[mask]
        self.acg = self.acg[mask]
        self.targets = self.targets[mask]
        self.info = np.array(self.info)[mask].tolist()
        self.spikes_list = np.array(self.spikes_list, dtype=object)[mask].tolist()
        self.labels_list = np.array(self.labels_list)[mask].tolist()

        if hasattr(self, "amplitudes_list"):
            self.amplitudes_list = np.array(self.amplitudes_list, dtype=object)[
                mask
            ].tolist()

    def make_unlabelled_only(self):
        """
        Removes all datapoints that have labels
        """
        mask = self.targets == -1
        self.wf = self.wf[mask]
        self.acg = self.acg[mask]
        self.targets = self.targets[mask]
        self.info = np.array(self.info)[mask].tolist()
        self.spikes_list = np.array(self.spikes_list, dtype=object)[mask].tolist()
        self.labels_list = np.array(self.labels_list)[mask].tolist()

        if hasattr(self, "amplitudes_list"):
            self.amplitudes_list = np.array(self.amplitudes_list, dtype=object)[
                mask
            ].tolist()

    def make_full_dataset(self, wf_only=False, acg_only=False):
        """
        This function takes the waveform and ACG data and concatenates them into a single array

        Args:
            wf_only: If True, only the waveform data will be used. Defaults to False
            acg_only: If True, only the ACG data will be used. Defaults to False
        """
        if wf_only:
            self.full_dataset = self.wf
        elif acg_only:
            self.full_dataset = self.acg
        else:
            self.full_dataset = np.concatenate((self.wf, self.acg), axis=1)

    def min_max_scale(self, mean=False, acg_only=True):
        """
        `min_max_scale` takes the waveform and ACG and scales them to the range [-1, 1] by dividing by the
        maximum absolute value of the waveform and ACG

        Args:
            mean: If True, the mean of the first 100 largest waveforms will be used as the scaling value.
            If False, the maximum value of the waveforms will be used. Defaults to False.
        """
        if mean:
            self._scale_value_wf = (np.sort(self.wf.ravel())[:100]).mean()
            self._scale_value_acg = (np.sort(self.acg.ravel())[-100:]).mean()
        else:
            self._scale_value_wf = np.max(np.abs(self.wf))
            self._scale_value_acg = np.max(np.abs(self.acg))

        if not acg_only:
            self.wf = self.wf / self._scale_value_wf
        self.acg = self.acg / self._scale_value_acg

    def filter_out_granule_cells(self):
        """
        Filters out granule cells from the dataset and returns new LABELLING and CORRESPONDENCE dictionaries for plotting.
        """

        granule_cell_mask = self.targets == LABELLING["GrC"]

        self.targets = (self.targets[~granule_cell_mask] - 1).astype(int)
        self.full_dataset = self.full_dataset[~granule_cell_mask]
        self.targets[self.targets < 0] = -1  # Reset the label of unlabeled cells
        self.wf = self.wf[~granule_cell_mask]
        self.acg = self.acg[~granule_cell_mask]
        self.info = np.array(self.info)[~granule_cell_mask].tolist()
        self.labels_list = np.array(self.labels_list)[~granule_cell_mask].tolist()
        self.spikes_list = np.array(self.spikes_list, dtype=object)[
            ~granule_cell_mask
        ].tolist()

        if hasattr(self, "amplitudes_list"):
            self.amplitudes_list = np.array(self.amplitudes_list, dtype=object)[
                ~granule_cell_mask
            ].tolist()
        # To convert text labels to numbers
        new_labelling = {
            "PkC_cs": 4,
            "PkC_ss": 3,
            "MFB": 2,
            "MLI": 1,
            "GoC": 0,
            "unlabelled": -1,
        }
        new_correspondence = {
            4: "PkC_cs",
            3: "PkC_ss",
            2: "MFB",
            1: "MLI",
            0: "GoC",
            -1: "unlabelled",
        }
        return new_labelling, new_correspondence

    def wvf_from_info(self, dp, unit):
        info_path = dp + "/" + str(unit)
        assert info_path in self.info, "No neuron for the dp and unit provided"

        idx = self.info.index(info_path)

        return self.wf[idx].reshape(self._n_channels, self._central_range)

    def train_from_info(self, dp, unit):
        info_path = dp + "/" + str(unit)
        assert info_path in self.info, "No neuron for the dp and unit provided"

        idx = self.info.index(info_path)

        return self.spikes_list[idx]

    def plot_from_info(self, dp, unit):
        info_path = dp + "/" + str(unit)
        assert info_path in self.info, "No neuron for the dp and unit provided"

        wvf = self.wvf_from_info(dp, unit)
        train = self.train_from_info(dp, unit)

        npyx.plot.plt_wvf(wvf.T)
        plt.show()
        npyx.plot.plot_acg("hello", 0, train=train)
        plt.show()

    def __len__(self):
        return len(self.wf)


def merge_datasets(*args: NeuronsDataset) -> NeuronsDataset:
    """Merges multiple NeuronsDatasets instances into one"""
    new_dataset = copy.deepcopy(args[0])
    for dataset in args[1:]:
        assert isinstance(dataset, NeuronsDataset)
        new_dataset.wf = np.vstack((new_dataset.wf, dataset.wf))
        new_dataset.acg = np.vstack((new_dataset.acg, dataset.acg))
        new_dataset.targets = np.hstack((new_dataset.targets, dataset.targets))
        new_dataset.info = np.hstack(
            (np.array(new_dataset.info), np.array(dataset.info))
        ).tolist()
        new_dataset.spikes_list = np.hstack(
            (
                np.array(new_dataset.spikes_list, dtype=object),
                np.array(dataset.spikes_list, dtype=object),
            )
        ).tolist()
        new_dataset.discarded_df = pd.concat(
            (new_dataset.discarded_df, dataset.discarded_df), axis=0
        )
        new_dataset.labels_list = new_dataset.labels_list + dataset.labels_list

        if hasattr(new_dataset, "amplitudes_list"):
            new_dataset.amplitudes_list = (
                new_dataset.amplitudes_list + dataset.amplitudes_list
            )
    return new_dataset
