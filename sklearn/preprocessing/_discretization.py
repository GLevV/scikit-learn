# -*- coding: utf-8 -*-

# Author: Henry Lin <hlin117@gmail.com>
#         Tom Dupré la Tour

# License: BSD


import numbers
import numpy as np
import warnings

from . import OneHotEncoder

from ..base import BaseEstimator, TransformerMixin
from ..utils.validation import check_array
from ..utils.validation import check_is_fitted
from ..utils.validation import _deprecate_positional_args


class KBinsDiscretizer(TransformerMixin, BaseEstimator):
    """
    Bin continuous data into intervals.

    Read more in the :ref:`User Guide <preprocessing_discretization>`.

    .. versionadded:: 0.20

    Parameters
    ----------
    n_bins : {int, array-like (n_features,), dtype=integral, 'auto'}, default=5
        The number of bins to produce. Raises ValueError if ``n_bins < 2``.
        For 'auto' option Sturges formula is used: bins are log(n_samples) + 1.

        .. versionadded:: 0.24
            Added 'auto' option

    encode : {'onehot', 'onehot-dense', 'ordinal'}, default='onehot'
        Method used to encode the transformed result.

        onehot
            Encode the transformed result with one-hot encoding
            and return a sparse matrix. Ignored features are always
            stacked to the right.
        onehot-dense
            Encode the transformed result with one-hot encoding
            and return a dense array. Ignored features are always
            stacked to the right.
        ordinal
            Return the bin identifier encoded as an integer value.

    strategy : {'uniform', 'quantile', 'kmeans'}, default='quantile'
        Strategy used to define the widths of the bins.

        uniform
            All bins in each feature have identical widths.
        quantile
            All bins in each feature have the same number of points.
        kmeans
            Values in each bin have the same nearest center of a 1D k-means
            cluster.

    dtype : {np.float32, np.float64}, default=None
        The desired data-type for the output. If None, output dtype is
        consistent with input dtype. Only np.float32 and np.float64 are
        supported.

        .. versionadded:: 0.24

    Attributes
    ----------
    n_bins_ : ndarray of shape (n_features,), dtype=np.int_
        Number of bins per feature. Bins whose width are too small
        (i.e., <= 1e-8) are removed with a warning.

    bin_edges_ : ndarray of ndarray of shape (n_features,)
        The edges of each bin. Contain arrays of varying shapes ``(n_bins_, )``
        Ignored features will have empty arrays.

    See Also
    --------
    Binarizer : Class used to bin values as ``0`` or
        ``1`` based on a parameter ``threshold``.

    Notes
    -----
    In bin edges for feature ``i``, the first and last values are used only for
    ``inverse_transform``. During transform, bin edges are extended to::

      np.concatenate([-np.inf, bin_edges_[i][1:-1], np.inf])

    You can combine ``KBinsDiscretizer`` with
    :class:`~sklearn.compose.ColumnTransformer` if you only want to preprocess
    part of the features.

    ``KBinsDiscretizer`` might produce constant features (e.g., when
    ``encode = 'onehot'`` and certain bins do not contain any data).
    These features can be removed with feature selection algorithms
    (e.g., :class:`~sklearn.feature_selection.VarianceThreshold`).

    Examples
    --------
    >>> X = [[-2, 1, -4,   -1],
    ...      [-1, 2, -3, -0.5],
    ...      [ 0, 3, -2,  0.5],
    ...      [ 1, 4, -1,    2]]
    >>> est = KBinsDiscretizer(n_bins=3, encode='ordinal', strategy='uniform')
    >>> est.fit(X)
    KBinsDiscretizer(...)
    >>> Xt = est.transform(X)
    >>> Xt  # doctest: +SKIP
    array([[ 0., 0., 0., 0.],
           [ 1., 1., 1., 0.],
           [ 2., 2., 2., 1.],
           [ 2., 2., 2., 2.]])

    Sometimes it may be useful to convert the data back into the original
    feature space. The ``inverse_transform`` function converts the binned
    data into the original feature space. Each value will be equal to the mean
    of the two bin edges.

    >>> est.bin_edges_[0]
    array([-2., -1.,  0.,  1.])
    >>> est.inverse_transform(Xt)
    array([[-1.5,  1.5, -3.5, -0.5],
           [-0.5,  2.5, -2.5, -0.5],
           [ 0.5,  3.5, -1.5,  0.5],
           [ 0.5,  3.5, -1.5,  1.5]])

    """

    @_deprecate_positional_args
    def __init__(self, n_bins='warn', *, encode='onehot', strategy='quantile',
                 dtype=None):
        self.n_bins = n_bins
        self.encode = encode
        self.strategy = strategy
        self.dtype = dtype

    def fit(self, X, y=None):
        """
        Fit the estimator.

        Parameters
        ----------
        X : array-like of shape (n_samples, n_features)
            Data to be discretized.

        y : None
            Ignored. This parameter exists only for compatibility with
            :class:`~sklearn.pipeline.Pipeline`.

        Returns
        -------
        self
        """
        if self.n_bins == 'warn':
            warnings.warn("The default value of n_bins will change from "
                          "5 to 'auto' in 0.25.", FutureWarning)
        X = self._validate_data(X, dtype='numeric')

        supported_dtype = (np.float64, np.float32)
        if self.dtype in supported_dtype:
            output_dtype = self.dtype
        elif self.dtype is None:
            output_dtype = X.dtype
        else:
            raise ValueError(
                f"Valid options for 'dtype' are "
                f"{supported_dtype + (None,)}. Got dtype={self.dtype} "
                f" instead."
            )
        valid_encode = ('onehot', 'onehot-dense', 'ordinal')
        if self.encode not in valid_encode:
            raise ValueError(
                f"Valid options for 'encode' are {valid_encode}. "
                f"Got encode={self.encode!r} instead."
            )
        valid_strategy = ('uniform', 'quantile', 'kmeans')
        if self.strategy not in valid_strategy:
            raise ValueError(
                f"Valid options for 'strategy' are {valid_strategy}. "
                f"Got strategy={self.strategy!r} instead."
            )

        n_features = X.shape[1]
        n_samples = X.shape[0]
        n_bins = self._validate_n_bins(n_features, n_samples)

        bin_edges = np.zeros(n_features, dtype=object)
        for jj in range(n_features):
            column = X[:, jj]
            col_min, col_max = column.min(), column.max()

            if col_min == col_max:
                warnings.warn(f"Feature {jj} is constant and will be "
                              f"replaced with 0.")
                n_bins[jj] = 1
                bin_edges[jj] = np.array([-np.inf, np.inf])
                continue

            if self.strategy == 'uniform':
                bin_edges[jj] = np.linspace(col_min, col_max, n_bins[jj] + 1)

            elif self.strategy == 'quantile':
                quantiles = np.linspace(0, 100, n_bins[jj] + 1)
                bin_edges[jj] = np.asarray(np.percentile(column, quantiles))

            elif self.strategy == 'kmeans':
                from ..cluster import KMeans  # fixes import loops

                # Deterministic initialization with uniform spacing
                uniform_edges = np.linspace(col_min, col_max, n_bins[jj] + 1)
                init = (uniform_edges[1:] + uniform_edges[:-1])[:, None] * 0.5

                # 1D k-means procedure
                km = KMeans(n_clusters=n_bins[jj], init=init,
                            n_init=1, algorithm='full')
                centers = km.fit(column[:, None]).cluster_centers_[:, 0]
                # Must sort, centers may be unsorted even with sorted init
                centers.sort()
                bin_edges[jj] = (centers[1:] + centers[:-1]) * 0.5
                bin_edges[jj] = np.r_[col_min, bin_edges[jj], col_max]

            # Remove bins whose width are too small (i.e., <= 1e-8)
            if self.strategy in ('quantile', 'kmeans'):
                mask = np.ediff1d(bin_edges[jj], to_begin=np.inf) > 1e-8
                bin_edges[jj] = bin_edges[jj][mask]
                if len(bin_edges[jj]) - 1 != n_bins[jj]:
                    warnings.warn(f"Bins whose width are too small "
                                  f"(i.e., <= 1e-8) in feature {jj} "
                                  f"are removed. Consider decreasing "
                                  f"the number of bins.")
                    n_bins[jj] = len(bin_edges[jj]) - 1

        self.bin_edges_ = bin_edges
        self.n_bins_ = n_bins

        if 'onehot' in self.encode:
            self._encoder = OneHotEncoder(
                categories=[np.arange(i) for i in self.n_bins_],
                sparse=self.encode == 'onehot',
                dtype=output_dtype)
            # Fit the OneHotEncoder with toy datasets
            # so that it's ready for use after the KBinsDiscretizer is fitted
            self._encoder.fit(np.zeros((1, len(self.n_bins_))))

        return self

    def _validate_n_bins(self, n_features, n_samples):
        """Returns n_bins_, the number of bins per feature.
        """
        orig_bins = self.n_bins
        if isinstance(orig_bins, numbers.Number) or isinstance(orig_bins, str):
            if orig_bins == 'auto':
                # calculate number of bins with Sturges rule
                orig_bins = int(np.ceil(np.log2(n_samples) + 1.))
            if orig_bins == 'warn:
                # deprecation cycle case, should be deleted afterwards
                orig_bins = 5
            if not isinstance(orig_bins, numbers.Integral):
                raise ValueError(
                    f"{KBinsDiscretizer.__name__} received "
                    f"an invalid n_bins type. Received "
                    f"{type(orig_bins).__name__}, expected int or 'auto'."
                )
            if orig_bins < 2:
                raise ValueError(
                    f"{KBinsDiscretizer.__name__} received an invalid number "
                    f"of bins. Received {orig_bins}, expected at least 2."
                )
            return np.full(n_features, orig_bins, dtype=int)

        n_bins = check_array(orig_bins, dtype=int, copy=True,
                             ensure_2d=False)

        if n_bins.ndim > 1 or n_bins.shape[0] != n_features:
            raise ValueError("n_bins must be a scalar or array "
                             "of shape (n_features,).")

        bad_nbins_value = (n_bins < 2) | (n_bins != orig_bins)

        violating_indices = np.where(bad_nbins_value)[0]
        if violating_indices.shape[0] > 0:
            indices = ", ".join(str(i) for i in violating_indices)
            raise ValueError(
                f"{KBinsDiscretizer.__name__} received an invalid number "
                f"of bins at indices {indices}. Number of bins "
                f"must be at least 2, and must be an int."
            )
        return n_bins

    def transform(self, X):
        """
        Discretize the data.

        Parameters
        ----------
        X : array-like of shape (n_samples, n_features)
            Data to be discretized.

        Returns
        -------
        Xt : {ndarray, sparse matrix}, dtype={np.float32, np.float64}
            Data in the binned space. Will be a sparse matrix if
            `self.encode='onehot'` and ndarray otherwise.
        """
        check_is_fitted(self)

        # check input and attribute dtypes
        dtype = (np.float64, np.float32) if self.dtype is None else self.dtype
        Xt = self._validate_data(X, copy=True, dtype=dtype, reset=False)

        bin_edges = self.bin_edges_
        for jj in range(Xt.shape[1]):
            # Values which are close to a bin edge are susceptible to numeric
            # instability. Add eps to X so these values are binned correctly
            # with respect to their decimal truncation. See documentation of
            # numpy.isclose for an explanation of ``rtol`` and ``atol``.
            rtol = 1.e-5
            atol = 1.e-8
            eps = atol + rtol * np.abs(Xt[:, jj])
            Xt[:, jj] = np.digitize(Xt[:, jj] + eps, bin_edges[jj][1:])
        np.clip(Xt, 0, self.n_bins_ - 1, out=Xt)

        if self.encode == 'ordinal':
            return Xt

        dtype_init = None
        if 'onehot' in self.encode:
            dtype_init = self._encoder.dtype
            self._encoder.dtype = Xt.dtype
        try:
            Xt_enc = self._encoder.transform(Xt)
        finally:
            # revert the initial dtype to avoid modifying self.
            self._encoder.dtype = dtype_init
        return Xt_enc

    def inverse_transform(self, Xt):
        """
        Transform discretized data back to original feature space.

        Note that this function does not regenerate the original data
        due to discretization rounding.

        Parameters
        ----------
        Xt : array-like of shape (n_samples, n_features)
            Transformed data in the binned space.

        Returns
        -------
        Xinv : ndarray, dtype={np.float32, np.float64}
            Data in the original feature space.
        """
        check_is_fitted(self)

        if 'onehot' in self.encode:
            Xt = self._encoder.inverse_transform(Xt)

        Xinv = check_array(Xt, copy=True, dtype=(np.float64, np.float32))
        n_features = self.n_bins_.shape[0]
        if Xinv.shape[1] != n_features:
            raise ValueError(
                f"Incorrect number of features. Expecting {n_features}, "
                f"received {Xinv.shape[1]}."
            )

        for jj in range(n_features):
            bin_edges = self.bin_edges_[jj]
            bin_centers = (bin_edges[1:] + bin_edges[:-1]) * 0.5
            Xinv[:, jj] = bin_centers[np.int_(Xinv[:, jj])]

        return Xinv
