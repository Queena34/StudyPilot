# Regularization

L1 regularization adds the absolute values of model coefficients to the loss function. It often drives some coefficients exactly to zero, so it can produce sparse models and perform feature selection.

L2 regularization adds the squared values of coefficients to the loss function. It usually shrinks coefficients toward zero without making them exactly zero and is useful when many features contribute to the prediction.

正则化用于限制模型复杂度、降低过拟合风险。L1 更容易产生稀疏参数，L2 通常让参数整体平滑地缩小。
