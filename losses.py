import torch.nn as nn
import torch.nn.functional as F
import torch
from utils import ConjugateDualFunction


class fDALLoss(nn.Module):
    def __init__(self, divergence_name, gamma):
        super(fDALLoss, self).__init__()

        self.lhat = None
        self.phistar = None
        self.phistar_gf = None
        self.multiplier = 1.  # Modified..... orginally 1.0 then 1.87
        self.internal_stats = {}
        self.domain_discriminator_accuracy = -1

        self.gammaw = gamma
        self.phistar_gf = lambda t: ConjugateDualFunction(divergence_name).fstarT(t)
        self.gf = lambda v: ConjugateDualFunction(divergence_name).T(v)

    def forward(self, y_s, y_t, y_s_adv, y_t_adv, K):
        # ---

        v_s = y_s_adv # h' output [4, 2, 200, 200]
        v_t = y_t_adv
        
        if K > 1:
            _, prediction_s = y_s.max(dim=1) # index which is max in h(x)   [4, 200, 200] 0 or 1
            _, prediction_t = y_t.max(dim=1)

            v_s = -F.nll_loss(v_s, prediction_s.detach(), reduction='none')  # vs = [4, 0, 200, 200] 0 if pred 0 otherwise 1
            # picking element prediction_t k element from y_t_adv.
            v_t = -F.nll_loss(v_t, prediction_t.detach(), reduction='none')

        dst = torch.mean(torch.mean(self.gf(v_s))) - torch.mean(torch.mean(self.phistar_gf(v_t)))
        # dst = torch.mean(torch.mean(self.gf(v_s), dim = (-2,-1))) - torch.mean(torch.mean(self.phistar_gf(v_t), dim = (-2,-1)))
        #F: Why Dim???
        
        self.internal_stats['lhatsrc'] = torch.mean(v_s).item()
        self.internal_stats['lhattrg'] = torch.mean(v_t).item()
        self.internal_stats['acc'] = self.domain_discriminator_accuracy
        self.internal_stats['dst'] = dst.item()

        return -self.multiplier * dst #multiplier = 1.87 - 1 again