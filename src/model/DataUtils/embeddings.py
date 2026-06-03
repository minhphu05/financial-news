import torch

def build_embedding_matrix(vocab, ft_model, embedding_dim=300):
    matrix = torch.zeros((vocab.vocab_size, embedding_dim))

    for word, idx in vocab.word2idx.items():
        matrix[idx] = torch.tensor(ft_model.get_word_vector(word))

    return matrix