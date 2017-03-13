# -*- coding: utf-8 -*-

import numpy as np
#from numpy.linalg import eigvalsh, eigh
from scipy.sparse.linalg import eigsh
from scipy.sparse import issparse,  csr_matrix, isspmatrix, isspmatrix_csr
import networkx as nx
from networkx.algorithms import bipartite
import matplotlib.pyplot as plt
import mpl_toolkits.mplot3d.art3d as art3d
import os
from time import gmtime, strftime
import time
from sklearn.preprocessing import normalize
from sklearn.metrics import precision_recall_curve, average_precision_score, auc


def graph_diff(Laplacian, Laplacian_est):
    if np.linalg.norm(Laplacian_est-Laplacian_est.T, 'fro') > 1e-5:
        raise ValueError("Laplacian_estimate must be symmetric")
        
    n = Laplacian.shape[0]
    n_e = Laplacian_est.shape[0]
    if n != n_e:
        raise ValueError("Dimension of Laplacian must be equal to "+ str(n)+"x" + str(n)+".")
   
    Laplacian_binary = np.sign(abs(Laplacian))
    Laplacian_est_binary = np.sign(abs(Laplacian_est))
    diff = sum(sum(abs(np.triu(Laplacian_binary, 1) - np.triu(Laplacian_est_binary, 1))))
    total_triu = n*(n-1)/2
    return (diff, diff/total_triu)

def glasso_nonzero_ratio(precision):
        
    n = precision.shape[0]
    precision_binary = np.sign(abs(precision))
    nonzeros = sum(sum(abs(np.triu(precision_binary, 0))))
    total_triu = n*(n-1)/2
    return (nonzeros, float(nonzeros)/float(total_triu))

def graph_comparison_norm(Laplacian, Laplacian_est, norm_type='fro'):
    return np.linalg.norm(Laplacian - Laplacian_est, norm_type)/np.linalg.norm(Laplacian, norm_type)



def graph_precision_recall_curve(Laplacian, Laplacian_est):
    if np.linalg.norm(Laplacian_est-Laplacian_est.T, 'fro') > 1e-5:
        raise ValueError("Laplacian_estimate must be symmetric")
        
    n = Laplacian.shape[0]
    n_e = Laplacian_est.shape[0]
    if n != n_e:
        raise ValueError("Dimension of Laplacian must be equal to "+ str(n)+"x" + str(n)+".")
    from scipy.special import betainc
    Laplacian_binary = np.triu(np.sign(abs(Laplacian)))
    #Laplacian_est[np.where(abs(Laplacian_est) > 1)] /= abs(Laplacian_est[np.where(abs(Laplacian_est) > 1)])
    Laplacian_est_binary = 1- (1-abs(Laplacian_est))**2 #betainc(0.5, 0.5, np.sign(abs(Laplacian_est))) #1- (1-abs(Laplacian_est))**2

    # compare the off-diagnoal term
    y_true = np.squeeze(Laplacian_binary[np.triu_indices(n, k=1)])
    prob_pred = np.squeeze(Laplacian_est_binary[np.triu_indices(n, k=1)])
    #print(np.squeeze(y_true).shape)
    #print(prob_pred.shape)
    precision, recall, thresholds = precision_recall_curve(y_true, prob_pred)
    average_precision = average_precision_score(y_true, prob_pred)
    auc_pre_recall = auc(recall, precision)
    return (precision, recall, average_precision, auc_pre_recall)


#===============================================================
class latent_signal_network:

   
    def __init__ (self, size, prob, option):

        try:
            self.seed = option['seed']
        except KeyError:
            self.seed = None

        try:
            self.node_dim = option['node_dim']
        except KeyError:
            self.node_dim = 2

        try:
            self.model_name = option['model']
        except KeyError:
            self.model_name = newman

        try:
            self.k_u = option['cutoff_freq']
        except KeyError:
            self.k_u = 10

        self.prob = prob
        self.size = size
        # if already written 
        self.ifwrite = False



    def graph_from_sparse_adjmat(self, adjMat):
        if not isspmatrix(adjMat):
            adjMat = csr_matrix(adjMat)
        G = nx.from_scipy_sparse_matrix(adjMat) 
        return G 



    def graph_build(self, size, prob, option, node_color=None, write_graph=False, save_fig=False):
        '''
            build graph with two random partition. prob = [p_in, p_out], within-cluster edge prob and between-cluster edge prob. 

         option['model']

                  ="partition", random partition graph 
                      then  
                          size = [size_c1, size_c2, ..., size_ck] for ck clusters
                          prob = [p_in, p_out]

                  ="newman", Newman-Watts-Strogatz graph, small world ring graph
                          size = number of nodes
                          prob = probability of adding a new edge for each edge
                          option['k-NN'] = k, Each node is joined with its k nearest neighbors in a ring topology.

                  ="binomial", Erdős-Rényi graph or binomial graph
                          size = number of nodes
                          prob = probability of adding a new edge 

                  ="power", Power-Law cluster graph 
                          size = [n,m] where n = nodes, m = edges for each node
                          prob = probability of adding a triangle after adding a random edge

                  ="grid", Grid-2D graph
                          size = [m,n] where mxn nodes for 2D grid
 
                  ='tree', a tree whose degree follows power-law distribution
                          size = number of total nodes
                          option['gamma'] = power ratio

                  ='balanced_tree', a balanced tree with r branches and h depth
                          option['r'] = branches for each node
                          option['h'] = depth of the tree

                  ='random_bipartite_binomial', a bipartite version of the binomial (Erdős-Rényi) graph.
                          size = [n, m], n and m are node size of two clusters 
                          prob = probability of adding an edge between two clusters
                          must import nx.algorithm.bipartite
                          should be a connected graph

                  ='random_bipartite_uniform', a bipartite version of the binomial (Erdős-Rényi) graph.
                          size = [n, m], n and m are node size of two clusters 
                          option['num_edges'] = number of edges selected that connect two clusters
                          must import nx.algorithm.bipartite
                          should be a connected graph
                  
 
         option['seed'] for random seed 
         option['node_dim'] for the dimension of node attributes
        '''
        seed = option['seed']
        node_dim = option['node_dim']
        #===========================================================================
        if option['model'] == 'partition': 
            if len(prob) < 2:
                p_in = prob
                p_out = 1 - p_in
           
            [p_in, p_out] = prob
            G = nx.random_partition_graph(sizes=size, p_in=p_in, p_out=p_out, seed=seed, directed=False)
            pos = nx.nx_pydot.graphviz_layout(G)
            fig1 = plt.figure(1)
            if node_color is None:
                node_color = ['r']*size[0]+['b']*size[1]

            nx.draw(G, pos=pos, arrows=False, with_labels=True, fontsize= 10, node_color=node_color, font_color='w')
            filename = "../figures/" +  strftime("%d%m%Y_%H%M%S", gmtime()) + "_netTop.eps"
            if save_fig == True:
                fig1.savefig(filename, format="eps")
             

        elif option['model'] == 'newman':
            try:
                k = option['k-NN']
            except KeyError:
                k = 2

            if type(size) == list:
                size = sum(size)

            G=  nx.newman_watts_strogatz_graph(size, k=k, p=prob, seed=seed)
            pos = nx.circular_layout(G, dim=2, scale=1.0, center=None)
            fig1 = plt.figure(1)
            if node_color is None:
                node_color = ['r']*size
            nx.draw(G, pos=pos, arrows=False, with_labels=True, fontsize= 10, node_color=node_color, font_color='w')
            filename = "../figures/" +  strftime("%d%m%Y_%H%M%S", gmtime()) + "_netTop.eps"
            if save_fig == True:
                fig1.savefig(filename, format="eps")

        elif option['model'] == 'binomial':
            if prob <= 0.2:
                G = nx.fast_gnp_random_graph(size, prob, seed=seed)
            else:
                G = nx.gnp_random_graph(size, prob, seed=seed)  
         
            if not nx.is_connected(G): #must be connected
                raise ValueError("Not connected. Please increase the edge probability.")

            if type(size) == list:
                size = sum(size)
            pos = nx.nx_pydot.graphviz_layout(G)
            fig1 = plt.figure(1)
            if node_color is None:
                node_color = ['r']*size
            nx.draw(G, pos=pos, arrows=False, with_labels=True, fontsize= 10, node_color=node_color, font_color='w')
            filename = "../figures/" +  strftime("%d%m%Y_%H%M%S", gmtime()) + "_netTop.eps"
            if save_fig == True:
                fig1.savefig(filename, format="eps")

        elif option['model'] == 'power':
            G = nx.powerlaw_cluster_graph(n=size[0], m=size[1], p=prob, seed=seed)
            pos = nx.nx_pydot.graphviz_layout(G)
            fig1 = plt.figure(1)
            nx.draw(G, pos=pos, arrows=False, with_labels=True, fontsize= 10, node_color=['r']*size, font_color='w')
            filename = "../figures/" +  strftime("%d%m%Y_%H%M%S", gmtime()) + "_netTop.eps"
            if save_fig == True:
                fig1.savefig(filename, format="eps")


        elif option['model'] == 'grid':
            if type(size) == int:
                size = [size, size]
            G = nx.grid_2d_graph(m=size[0], n=size[1])
            pos = dict(zip(G.nodes(), [np.asarray(u) for u in G.nodes()]))
            fig1 = plt.figure(1)
            if node_color is None:
                node_color = ['r']*sum(size)
            nx.draw(G, pos=pos, arrows=False, with_labels=True, fontsize= 10, node_color=node_color, font_color='w')
            filename = "../figures/" +  strftime("%d%m%Y_%H%M%S", gmtime()) + "_netTop.eps"
            if save_fig == True:
                fig1.savefig(filename, format="eps")
        
        elif option['model'] == 'tree':
            try:
                gamma = option['gamma']
            except KeyError:
                gamma = 3
            tries = 10000
            G = nx.random_powerlaw_tree(n=size, gamma=gamma, seed=seed, tries=tries)
            pos = nx.circular_layout(G, dim=2, scale=1.0, center=None) #nx.shell_layout(G)#nx.spring_layout(G) #nx.nx_pydot.graphviz_layout(G)
            fig1 = plt.figure(1)
            if node_color is None:
                node_color = ['r']*size
            nx.draw(G, pos=pos, arrows=False, with_labels=True, fontsize= 10, node_color=node_color, font_color='w')
            filename = "../figures/" +  strftime("%d%m%Y_%H%M%S", gmtime()) + "_netTop.eps"
            if save_fig == True:
                fig1.savefig(filename, format="eps")
    
        elif option['model'] == 'balanced_tree':
            try:
                r = option['r']
            except KeyError:
                r = 2
            try:
                h = option['h']
            except KeyError:
                h = 3
            G = nx.balanced_tree(r=r, h=h, create_using=nx.Graph())
            pos = nx.nx_pydot.graphviz_layout(G)
            fig1 = plt.figure(1)
            if node_color is None:
                node_color = ['r']*len(pos)
            nx.draw(G, pos=pos, arrows=True, with_labels=True, fontsize= 8, node_color=node_color, font_color='w')
            filename = "../figures/" +  strftime("%d%m%Y_%H%M%S", gmtime()) + "_netTop.eps"
            if save_fig == True:
                fig1.savefig(filename, format="eps")


        elif option['model'] == 'bipartite_binomial':
            if type(size) == int:
                size = [10, 10]
            G = nx.algorithms.bipartite.random_graph(size[0], size[1], prob, seed=seed, directed=False)
            node_sets = nx.algorithms.bipartite.sets(G)
            pos = nx.nx_pydot.graphviz_layout(G, prog='dot')
            if not nx.is_connected(G): #must be connected
                raise ValueError("Not connected. Please increase the edge probability.")
            fig1 = plt.figure(1)
            if node_color is None:
                node_color = ['r']*size[0]+['b']*size[1]
            nx.draw(G, pos=pos, arrows=True, with_labels=True, fontsize= 8, node_color=node_color, font_color='w')
            filename = "../figures/" +  strftime("%d%m%Y_%H%M%S", gmtime()) + "_netTop.eps"
            if save_fig == True:
                fig1.savefig(filename, format="eps")


        elif option['model'] == 'bipartite_uniform':
            if type(size) == int:
                size = [10, 10]

            try:
                num_edges = option['num_edges']
            except KeyError:
                num_edges = size[0]*size[1]
 
            if num_edges > size[0]*size[1]:
                print("too many edges. reduce to " + str(size[0]*size[1]))
                num_edges = size[0]*size[1]

            G = nx.algorithms.bipartite.gnmk_random_graph(size[0], size[1], num_edges, seed=seed, directed=False)
            node_sets = nx.algorithms.bipartite.sets(G)
            pos = nx.nx_pydot.graphviz_layout(G, prog='dot')
            if not nx.is_connected(G): #must be connected
                raise ValueError("Not connected. Please increase the edge probability.")
            fig1 = plt.figure(1)
            if node_color is None:
                node_color = ['r']*size[0]+['b']*size[1]
            nx.draw(G, pos=pos, arrows=True, with_labels=True, fontsize= 8, node_color=node_color, font_color='w')
            filename = "../figures/" +  strftime("%d%m%Y_%H%M%S", gmtime()) + "_netTop.eps"
            if save_fig == True:
                fig1.savefig(filename, format="eps")


        #===========================================================================
        G_out = nx.Graph()
        # node initialization 
        G_out.add_nodes_from(G.nodes(), attributes=np.zeros((node_dim,)).T)
        G_out.add_edges_from(G.edges())
        # assign weight values 
        for u, v, e in G_out.edges(data=True):
            e['weight'] = 1

        if write_graph:
            self.G = G_out
            self.option = option.copy()

        return G_out



    def smooth_gsignal_generate(self, G, T, sigma, alpha=0, seed=1000, add_noise=False, write_data=False, option=None, show_plot=False):
        '''
           generate the node attributes in the graph associated with the network topology.
         G = Graph with "attributes" data for each node 
         T = maximum loops of smoothing 
         sigma = initialized noise-level 

        '''
    
        #initialization
        n = len(G)
        dim = len(G.node[G.nodes()[0]]['attributes'])
        X = np.ndarray((n,dim))

        if alpha > 1 :
            alpha = 1- np.exp(-alpha)
        elif alpha < 0:
            alpha = np.exp(alpha)
          
        np.random.seed(seed)
        X_r = sigma*np.random.randn(n, dim)/np.sqrt(n)
        #X_r = normalize(X_r, norm='l1', axis=0)

        for i, idx in enumerate(G.nodes()):
            #dim = len(G.node[idx]['attributes'])
            G.node[idx]['attributes'] = X_r[i,:]
            X[i,:] = G.node[idx]['attributes']
        
        #tempG2 = G.copy()
        #for i, idx in enumerate(G.nodes()):   
        #    G.node[idx]['attributes'] = tempG2.node[idx]['attributes'] - sum([tempG2.node[allnodes]['attributes'] for allnodes in tempG2])/n
        #    X[i,:] = G.node[idx]['attributes']
        #tempG2.clear()    

        if show_plot == True:    
            plt.figure(1)
            plt.subplot("511")
            plt.stem(np.arange(X.shape[0]),X[:,0])   
        
        if T > 5:
            sepT = int(T/5)
        else:
            sepT = 1
        hist_tv = np.zeros((T,))
        # run a smoothing process on network
        for t in range(T):
            tempG = G.copy()
            for i, idx in enumerate(G.nodes()):
                if len(tempG[idx]) != 0:
                    G.node[idx]['attributes'] = (1-alpha)*sum([tempG.node[neighbor]['attributes']/len(tempG[neighbor]) for neighbor in tempG[idx]]) + alpha*tempG.node[idx]['attributes']
                    if add_noise:
                         G.node[idx]['attributes'] += sigma*np.random.randn(dim)/np.sqrt(n) 
            
            # avoid all one features
            tempG2 = G.copy()
            for i, idx in enumerate(G.nodes()):
                G.node[idx]['attributes'] = tempG2.node[idx]['attributes'] - (sum([tempG2.node[allnodes]['attributes'] for allnodes in tempG2])/n)

    
            for i, d in G.nodes_iter(data=True):
                X[i,:] = d['attributes']

            #X = normalize(X, norm='l1', axis=0)          
            hist_tv[t] = self.compute_total_variation(G)

            if t%sepT == 0 and show_plot == True:
                plt.figure(1)
                print("Iteration: " + str(t+1))
                plt.subplot(str(int(T/sepT)+1)+"1"+str(int(t/sepT)+2))
                plt.stem(np.arange(X.shape[0]),X[:,0])
                plt.axis([0, 40, -6, 8])
    
        if show_plot == True:        
            plt.show()        

        if write_data == True:
            if option is None:
                raise ValueError('Option for graph generator must not be none.')
            self.G = G.copy()
            self.X = X.copy()
            self.option = option.copy()
            self.hist_tv = np.copy(hist_tv)
            self.ifwrite = True
        else:
            self.ifwrite = False 

        return [G, X, hist_tv]



    def smooth_gsignal_filter(self, G, option, sigma, seed=1000, add_noise=False, show_plot=False, save_fig=False, write_data =False):
        '''
             Apply graph filtering to initial random graph signal X0
                    X = T*X0
             where T is a linear operator based on either adjacency matrix or graph laplacian matrix

             T = U*g(Sigma)*U.T for eigendecomposition of matrix basis = U*Sigma*U.T 

             option['mat']
                       = 'adjacency_matrix': use Adjacency matrix as the matrix basis
                       = 'laplacian_matrix': use Normalized Graph Laplacian matrix as the matrix basis

             option['method']
                       = 'l0_threshold': enforce all eigval < option['threshold'] to be zero
                       = 'l1_threshold': apply soft-thresholding to all eigval < option['threshold']
                                         i.e. new_eigval = [eigval - threshold]_{+}
                       = 'polynomial':  
                                  define coeffs = [coeff0, coeff1, coeff2, ..., coeffd] for degree d polynomial
                                        coff0 + coeff1*x + coeff2*x**2 + ... + coffd*x**d
                                  apply polynomial to each eigval 
                       = 'sigmoid':
                                   eigval*1/(1+exp(rate(i-b)))-bias

                       = 'l0_renomalize': apply l0_threshold then add sum(residual_energy) to each remaining eigval
                       = 'rescale': new_eigval =  option['weights'] * eigval
                       = 'sigmoid_threshold':  eigma_new = soft_theshold(eigma_old*1/(1+exp(rate*(i+1-shift))), bias)
                       = 'inverse_sqrt': eigma_new = 1/sqrt(eigma_old+ epsilon) for eigma_old
                       = 'inverse_poly'
                                        coff0 + coeff1*x**-1 + coeff2*x**-2 + ... + coffd*x**-d

             return Graph G, transformed data X, and initial data X_r

        '''
        n = len(G)
        dim = len(G.node[G.nodes()[0]]['attributes'])
        X = np.ndarray((n,dim))
          
        np.random.seed(seed)
        X_r = sigma*np.random.randn(n, dim)/np.sqrt(n)
        #X_r = normalize(X_r, norm='l1', axis=0)
        for i, idx in enumerate(G.nodes()):
            #dim = len(G.node[idx]['attributes'])
            G.node[idx]['attributes'] = X_r[i,:]
            X[i,:] = G.node[idx]['attributes']
        
        #tempG2 = G.copy()
        #for i, idx in enumerate(G.nodes()):   
        #    G.node[idx]['attributes'] = tempG2.node[idx]['attributes'] - sum([tempG2.node[allnodes]['attributes'] for allnodes in tempG2])/n
        #    X[i,:] = G.node[idx]['attributes']
        #tempG2.clear()    

        transformed_eigvals, eigvecs, _ = self.graph_filter(G, X_r, option, show_plot, save_fig)
        #X = np.asarray(np.dot(np.dot(eigvecs, np.diag(transformed_eigvals)), np.dot(eigvecs.T, X)))
        X = np.dot(transformed_eigvals*eigvecs, np.dot(eigvecs.T, X))
        for i, idx in enumerate(G.nodes()):
            #dim = len(G.node[idx]['attributes'])
            G.node[idx]['attributes'] = X[i,:]

        if write_data:
            self.G = G.copy()
            self.X = np.copy(X)
            self.ifwrite = True
        else:
            self.ifwrite = False 
        return (G, X, X_r)



    def graph_filter(self, G, X0, option, show_plot=False, save_fig=False):
        '''
             Apply graph filtering to initial random graph signal X0
                    X = T*X0
             where T is a linear operator based on either adjacency matrix or graph laplacian matrix

             T = U*g(Sigma)*U.T for eigendecomposition of matrix basis = U*Sigma*U.T 

             option['mat']
                       = 'adjacency_matrix': use Adjacency matrix as the matrix basis
                       = 'laplacian_matrix': use Normalized Graph Laplacian matrix as the matrix basis

             option['method']
                       = 'l0_threshold': enforce all eigval < option['threshold'] to be zero
                       = 'l1_threshold': apply soft-thresholding to all eigval < option['threshold']
                                         i.e. new_eigval = [eigval - threshold]_{+}
                       = 'polynomial':  
                                  define coeffs = [coeff0, coeff1, coeff2, ..., coeffd] for degree d polynomial
                                        coff0 + coeff1*x + coeff2*x**2 + ... + coffd*x**d
                                  apply polynomial to each eigval 
                       = 'sigmoid':
                                   eigval*1/(1+exp(rate(i-b)))-bias

                       = 'l0_renomalize': apply l0_threshold then add sum(residual_energy) to each remaining eigval
                       = 'rescale': new_eigval =  option['weights'] * eigval
                       = 'sigmoid_threshold':  eigma_new = soft_theshold(eigma_old*1/(1+exp(rate*(i+1-shift))), bias)
                       = 'inverse_sqrt': eigma_new = 1/sqrt(eigma_old+ epsilon) for eigma_old
                       = 'inverse_poly'
                                        coff0 + coeff1*x**-1 + coeff2*x**-2 + ... + coffd*x**-d

        '''
        if option['mat'] == 'adjacency_matrix':
            Mat = nx.adjacency_matrix(G, weight=None).todense()
            eigval_, eigvec_ = np.linalg.eigh(Mat)
            #for adjacency matrix in decreasing order
            eig_index = np.argsort(abs(eigval_))[::-1]            
            eigval = eigval_[eig_index]
            eigvec = eigvec_[:, eig_index]

        elif option['mat'] == 'laplacian_matrix':
            Mat = nx.normalized_laplacian_matrix(G, weight=None).todense()
            eigval_, eigvec_ = np.linalg.eigh(Mat)
            #for laplacian matrix in increasing order
            eig_index = np.argsort(eigval_)
            eigval = eigval_[eig_index]
            # find the inverse of laplacian
            #eigval[1:len(eigval)] = 1/eigval[1:len(eigval)]
            eigvec = eigvec_[:, eig_index]
            

        n = len(G)
        dim = len(G.node[G.nodes()[0]]['attributes'])

        if X0.shape[0] != n or X0.shape[1] != dim:
            X0 = np.random.randn(n, dim)
        
        if option['method'] == 'l0_threshold':
            try:
                tau = option['threshold'] 
            except KeyError:
                tau = 1
            import pywt
            transformed_eigval = pywt.threshold(eigval, tau, 'hard')

        elif option['method'] == 'l1_threshold':
            try:
                tau = option['threshold'] 
            except KeyError:
                tau = 1
            import pywt
            transformed_eigval = pywt.threshold(eigval, tau, 'soft')

        elif option['method'] == 'polynomial':
            try:
                coeffs = option['coeffs']
            except KeyError:
                coeffs = [0,1]
            def poly_fit(coeffs, sig):
                return sum([p*(sig**i) for i, p in enumerate(coeffs)])
            transformed_eigval = poly_fit(coeffs, eigval)

        elif option['method'] == 'sigmoid_threshold':
            try:
                rate = option['rate']
            except:
                rate = 1
           
            try:
                shift = option['shift']
            except:
                shift = 0

            try:
                bias = option['bias']
            except:
                bias = 0

            import pywt
            def sigmoid(x, rate, shift):
                return 1/(1+np.exp(rate*(x - shift)))
            
            transformed_eigval = pywt.threshold(eigval*sigmoid(1+np.arange(len(eigval)), rate, shift), bias, 'soft')

          
        elif option['method'] == 'l0_renormalize':
            try:
                tau = option['threshold'] 
            except KeyError:
                tau = 1
            index_less_l0 = np.where(eigval < tau)
            index_more_l0 = np.where(eigval >= tau)
            res = sum(eigval[index_less_l0])/len(eigval[index_more_l0])
            transformed_eigval = eigval.copy()
            transformed_eigval[index_less_l0] = 0
            transformed_eigval[index_more_l0] += res

        elif option['method'] == 'rescale':
            try:
               weights = option['weights']            
            except KeyError:
               weights = np.ones((len(eigval),))

            transformed_eigval = weights * eigval
        
        elif option['method'] == 'inverse_sqrt':
            try:
               eps = option['eps']
            except KeyError:
               eps = 1e-4

            nonzeros_indices = np.argwhere(eigval> 1e-4)
            transformed_eigval = eigval.copy()
            #print(eigval[nonzeros_indices])
            transformed_eigval[nonzeros_indices] = 1/np.sqrt(eps + transformed_eigval[nonzeros_indices])
            #transformed_eigval[eigval.argmin()] = 0

        elif option['method'] == 'inverse_poly':
            try:
                coeffs = option['coeffs']
            except KeyError:
                coeffs = [0,1]
            def poly_fit(coeffs, sig):
                return sum([p*(sig**i) for i, p in enumerate(coeffs)])
            nonzeros_indices = np.argwhere(eigval> 1e-4)
            transformed_eigval = eigval.copy()
            #print(eigval[nonzeros_indices])
            transformed_eigval[nonzeros_indices] = 1/transformed_eigval[nonzeros_indices]
            transformed_eigval = poly_fit(coeffs, transformed_eigval)

        if show_plot:
            fig = plt.figure(figsize=(15,6))
            ax1 = fig.add_subplot(121)
            (markerline, stemlines, baseline) = plt.stem(np.arange(len(eigval)), eigval, 'b', basefmt='k-')
#            plt.plot(np.arange(len(eigval)), np.ones((len(eigval, ))), '-r')
#            if option['mat'] == 'adjacency_matrix':
#               plt.plot(np.arange(len(eigval)), -np.ones((len(eigval, ))), '-r')
            plt.xlabel('rank of eigenvalue')
            plt.ylabel('eigenvalue')
            ax1.grid(True)

            ax2 = fig.add_subplot(122)
            (markerline, stemlines, baseline) = plt.stem(np.arange(len(transformed_eigval)), transformed_eigval, 'b', basefmt='k-')
#            plt.plot(np.arange(len(eigval)), np.ones((len(eigval, ))), '-r')
            plt.xlabel('rank of eigenvalue')
            plt.ylabel('eigenvalue')
            ax2.grid(True)
            plt.show()
            filename = "../figures/"+strftime("%d%m%Y_%H%M%S", gmtime()) + "_eigenvalue_transform.eps"
            if save_fig : fig.savefig(filename)

        return (transformed_eigval, np.asarray(eigvec), eigval) 


    def get_normalized_laplacian(self, G, weight=None):
        laplacian = nx.normalized_laplacian_matrix(G, weight=weight).todense()
        return np.asarray(laplacian)


    def eigsh_laplacian(self, G, k=5):
        if k > len(G):
            k = len(G)
        laplacian = nx.normalized_laplacian_matrix(G)
        eigval, eigvec = eigsh(laplacian, k, which='SM')
        return (eigval, eigvec)#[:, [1:len(eigval)]])

    def graph_fourier_transform(self, G, X, show_fig=False, save_fig=False, overwrite=False):
        
        _, U_k = self.eigsh_laplacian(G, self.k_u)
        gft = np.dot(U_k.T, X)
        if overwrite: self.X_f = gft
        if show_fig:
            fig = plt.figure(figsize=(15, 6))
            ax1  = fig.add_subplot(1,2,1)
            val  = X[:,0]
            markerline, stemlines, baseline = plt.stem(np.arange(len(val)), val,'b')
            plt.xlim([-0.1, len(val)+0.1])
            plt.xlabel('node index')
            plt.ylabel('graph signal')

            ax2 =  fig.add_subplot(1,2,2)
            val =  gft[:,0]
            markerline2, stemlines2, baseline2 = plt.stem(np.arange(len(val)),val,'b')
            plt.xlim([-0.1, len(val)+0.1])
            plt.xlabel('graph freq. comp')
            plt.ylabel('magnitude of graph Fourier transform')

            filename = "../figures/" +  strftime("%d%m%Y_%H%M%S", gmtime()) + "_gft.eps"
            if save_fig :
                fig.savefig(filename, format="eps")
                 

        return gft






    def inference_hidden_graph_regul(self, G,  sigma, init_X=None):
        # find the latent variables in factor analysis model
        #   h = arg min 0.5*|| x - U*h||**2 + (0.5/sigma**2)*h.T*Lambda*h 
        if init_X is not None:
            X = init_X
        else: 
            if self.ifwrite:
                X = self.X
            else:
                X = np.random.randn(len(G), self.node_dim)
    

        lambda_k, U_k = self.eigsh_laplacian(G, self.k_u)#[:, 0:self.k_u]
        shinkage = lambda_k/sigma**2 + np.ones(lambda_k.shape)

        h = (np.dot(U_k.T, X).T/shinkage).T
        return h


    def get_node_attributes(self, G):
        n = len(G)
        dim = len(G.node[G.nodes()[0]]['attributes'])
        X = np.zeros((n,dim))
        idx_x = 0
        for i, data in G.nodes_iter(data=True):
            X[idx_x,:] = data['attributes']
            idx_x += 1

        nodeIdx = [{'node': idx, 'loc' : i} for i, idx in enumerate(G.nodes())]
        return [X, nodeIdx]


    def compute_laplacian_smoothness(self, G):
        total_diff = 0
        m = G.size()
        sum_weight = 0
        for node1, node2, data in G.edges_iter(data=True):
            total_diff = total_diff + data['weight']*np.linalg.norm(G.node[node1]['attributes']- G.node[node2]['attributes'])**2
            sum_weight = sum_weight + data['weight']
        return total_diff/sum_weight

    def compute_total_variation(self, G):
        total_variation = 0
        count = 0
        for i, idx in enumerate(G.nodes()):
            if len(G[idx]) != 0:
                temp_vec = sum([G.node[neighbor]['attributes']*G[idx][neighbor]['weight'] for neighbor in G[idx]])/sum([G[idx][neighbor]['weight'] for neighbor in G[idx]])
                total_variation = total_variation + np.linalg.norm(G.node[idx]['attributes'] - temp_vec)
                count = count + 1
        if count > 0:
            return total_variation/count
        else:
            return int(1e10)

    def get_edgelist(self, G):
        return G.edges()    



    def draw(self, G, option, pos=None, pos_init=None, fontsize=8, font_color = 'k', node_size = 8, save_fig = False):
        seed = option['seed']
        node_dim = option['node_dim']
        try:
            node_color = option['draw_node_color']
        except KeyError:
            node_color = ['r']*len(G)

        if len(node_color) != len(G):
            node_color = ['r']*len(G)

        try:
            scale = option['draw_scale']
        except KeyError:
            scale = 100
        #===========================================================================
        if option['model'] == 'partition': 
            pos = nx.nx_pydot.graphviz_layout(G)
            fig1 = plt.figure(1)
            nx.draw(G, pos=pos, arrows=False, with_labels=True, fontsize=fontsize, node_color=node_color, font_color=font_color, node_size=node_size)
            filename = "../figures/" +  strftime("%d%m%Y_%H%M%S", gmtime()) + "_netTop.eps"
            if save_fig == True:
                fig1.savefig(filename, format="eps")
             

        elif option['model'] == 'newman':
            pos = nx.circular_layout(G, dim=2, scale=scale, center=None)
            fig1 = plt.figure(1)
            nx.draw(G, pos=pos, arrows=False, with_labels=True, fontsize=fontsize, node_color=node_color, font_color=font_color, node_size=node_size)
            filename = "../figures/" +  strftime("%d%m%Y_%H%M%S", gmtime()) + "_netTop.eps"
            if save_fig == True:
                fig1.savefig(filename, format="eps")

        elif option['model'] == 'binomial':
            pos = nx.nx_pydot.graphviz_layout(G)
            fig1 = plt.figure(1)
            nx.draw(G, pos=pos, arrows=False, with_labels=True, fontsize=fontsize, node_color=node_color, font_color=font_color, node_size=node_size)
            filename = "../figures/" +  strftime("%d%m%Y_%H%M%S", gmtime()) + "_netTop.eps"
            if save_fig == True:
                fig1.savefig(filename, format="eps")

        elif option['model'] == 'power':
            pos = nx.nx_pydot.graphviz_layout(G)
            fig1 = plt.figure(1)
            nx.draw(G, pos=pos, arrows=False, with_labels=True, fontsize=fontsize, node_color=node_color, font_color=font_color, node_size=node_size)
            filename = "../figures/" +  strftime("%d%m%Y_%H%M%S", gmtime()) + "_netTop.eps"
            if save_fig == True:
                fig1.savefig(filename, format="eps")


        elif option['model'] == 'grid':
            pos = dict(zip(G.nodes(), [np.asarray(u) for u in G.nodes()]))
            fig1 = plt.figure(1)
            nx.draw(G, pos=pos, arrows=False, with_labels=True, fontsize=fontsize, node_color=node_color, font_color=font_color, node_size=node_size)
            filename = "../figures/" +  strftime("%d%m%Y_%H%M%S", gmtime()) + "_netTop.eps"
            if save_fig == True:
                fig1.savefig(filename, format="eps")
        
        elif option['model'] == 'tree':
            pos = nx.circular_layout(G, dim=2, scale=scale, center=None) #nx.shell_layout(G)#nx.spring_layout(G) #nx.nx_pydot.graphviz_layout(G)
            fig1 = plt.figure(1)
            nx.draw(G, pos=pos, arrows=False, with_labels=True, fontsize=fontsize, node_color=node_color, font_color=font_color, node_size=node_size)
            filename = "../figures/" +  strftime("%d%m%Y_%H%M%S", gmtime()) + "_netTop.eps"
            if save_fig == True:
                fig1.savefig(filename, format="eps")
    
        elif option['model'] == 'balanced_tree':
            pos = nx.nx_pydot.graphviz_layout(G)
            fig1 = plt.figure(1)
            nx.draw(G, pos=pos, arrows=True, with_labels=True, fontsize=fontsize, node_color=node_color, font_color=font_color, node_size=node_size)
            filename = "../figures/" +  strftime("%d%m%Y_%H%M%S", gmtime()) + "_netTop.eps"
            if save_fig == True:
                fig1.savefig(filename, format="eps")


        elif option['model'] == 'bipartite_binomial' or option['model'] == 'bipartite_uniform':
            node_sets = nx.algorithms.bipartite.sets(G)
            pos = nx.nx_pydot.graphviz_layout(G, prog='dot')
            if not nx.is_connected(G): #must be connected
                raise ValueError("Not connected. Please increase the edge probability.")
            fig1 = plt.figure(1)
            nx.draw(G, pos=pos, arrows=True, with_labels=True, fontsize=fontsize, node_color=node_color, font_color=font_color, node_size=node_size)
            filename = "../figures/" +  strftime("%d%m%Y_%H%M%S", gmtime()) + "_netTop.eps"
            if save_fig == True:
                fig1.savefig(filename, format="eps")

        else: 
            if pos is None:
                pos = nx.spring_layout(G, pos=pos_init, scale=scale, iterations=100) #nx.nx_pydot.graphviz_layout(G)

            fig1 = plt.figure(1)
            nx.draw(G, pos=pos, fontsize=fontsize, node_color=node_color, font_color=font_color, node_size=node_size)
            filename = "../figures/" +  strftime("%d%m%Y_%H%M%S", gmtime()) + "_netTop.eps"
            if save_fig == True:
                fig1.savefig(filename, format="eps")

        return pos


    def draw_degree_rank(G, save_fig=False):
        degree_sequence=sorted(nx.degree(G).values(),reverse=True) # degree sequence
        #print "Degree sequence", degree_sequence
        dmax=max(degree_sequence)
        fig3 = plt.figure(3) 
        plt.loglog(degree_sequence,'b-',marker='o')
        plt.title("Degree rank plot")
        plt.ylabel("degree")
        plt.xlabel("rank")
        
        # draw graph in inset
        plt.axes([0.45,0.45,0.45,0.45])
        Gcc=sorted(nx.connected_component_subgraphs(G), key = len, reverse=True)[0]
        pos=nx.spring_layout(Gcc)
        plt.axis('off')
        nx.draw_networkx_nodes(Gcc,pos,node_size=20)
        nx.draw_networkx_edges(Gcc,pos,alpha=0.4)
        
        filename = "../figures/"+strftime("%d%m%Y_%H%M%S", gmtime()) + "_degree_rank_plot.eps"
        #filename = "../figures/"+strftime("%d%m%Y_%H%M%S", gmtime()) + "_eigenvalue_adjMat.eps"
        if save_fig : fig3.savefig(filename)
        plt.show()





    def get_pos_graph(self, G, choice):
        if choice == 'newman' or choice == 'tree':
            pos=nx.circular_layout(G, dim=2, scale=1.0, center=None)
        elif choice == 'grid':
            pos=dict(zip(G.nodes(), [np.asarray(u) for u in G.nodes()]))
        elif 'bipartite' in choice:
            pos=nx.nx_pydot.graphviz_layout(G, prog='dot')
        else:
            pos=nx.nx_pydot.graphviz_layout(G, prog='neato')
        return pos



    def get_pos_coordinate(self, pos, nodeIdx=None):
        if nodeIdx is None:
            return np.array([[pos[key][0], pos[key][1]] for key in pos])
        else:
            return np.array([[pos[it['node']][0], pos[it['node']][1]] for it in nodeIdx])


    def plot_node_3d(self, pos_coordinates, edge_list,  node_values, view_angle, nodeIdx, columnIdx=0, figIdx=0, save_fig=False):  
        fig = plt.figure()
        ax = fig.add_subplot(1, 1, 1, projection='3d')
        [elev, azim] = view_angle
        ax.view_init(elev, azim)

        x = pos_coordinates[:,0]
        y = pos_coordinates[:,1]
        z = node_values[:,columnIdx]
        # plot a zero-plane
        Sx= np.linspace(min(x), max(x), 100)
        Sy= np.linspace(min(y), max(y), 100)
        SurfaceX, SurfaceY = np.meshgrid(Sx, Sy)
        SurfaceZ= np.zeros((len(Sx),))
        ax.plot_surface(SurfaceX,SurfaceY, SurfaceZ, rstride=8, cstride=8, alpha=0.05) 


        for edge in edge_list:
            n0_idx = next((item['loc'] for item in nodeIdx if item['node']== edge[0])) 
            n1_idx = next((item['loc'] for item in nodeIdx if item['node']== edge[1]))
            lx = np.array((x[n0_idx], x[n1_idx]))
            ly = np.array((y[n0_idx], y[n1_idx]))
            #print(lx)
            #print(ly)
            #print('----')
            line=art3d.Line3D(lx, ly, np.zeros((2,)), marker='o', markevery=(0, 1), markerfacecolor='r', color='k', linewidth=0.5)
            ax.add_line(line)
        # plot node and node-attributes in stem plot
        for xi, yi, zi in zip(x, y, z):        
            line=art3d.Line3D(*zip((xi, yi, 0), (xi, yi, zi)), marker='D', markevery=(1, 1), markerfacecolor='b', color='b',alpha=1)
            ax.add_line(line)
            #line=art3d.Line3D(*zip((xi, yi, zi), (xi, yi, 0)), marker='o', markevery=(1, 1), markerfacecolor='r', color='b', linewidth=1)
            #ax.add_line(line)
            #line=art3d.Line3D(*zip((xi, yi, 0), (xi, yi, zi)), marker='o', markevery=(1, 1), color='b')
            #ax.add_line(line)
         


        ax.set_xlim3d(min(x), max(x))
        ax.set_ylim3d(min(y), max(y))
        ax.set_zlim3d(min([min(z),-1]), max([max(z), 1])) 
        plt.show()
        #filename = "../figures/" +  strftime("%d%m%Y_%H%M%S", gmtime()) + "_netNode"+ str(figIdx) +".eps"
        #fig.savefig(filename, format='eps', dpi=1000)
        if save_fig == True:
            filename = "../figures/" +  strftime("%d%m%Y_%H%M%S", gmtime()) + "_netNode"+ str(figIdx) +".png"
            fig.savefig(filename)
        