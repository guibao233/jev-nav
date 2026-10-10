"""Meaningful geometry/planning regressions; synthetic CPU NavMesh, no API/GPU."""
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from clearance import ClearancePlanner, validate_reference_path
from prepare_clearance import main


class RectangleNavMesh:
    def __init__(self, width=4., height=2., block=None):
        self.width,self.height,self.block=width,height,block

    def is_navigable(self,p,max_y_delta=.5):
        x,y,z=p
        if abs(y)>max_y_delta or not (-1e-9<=x<=self.width+1e-9 and -1e-9<=z<=self.height+1e-9):return False
        return not (self.block and self.block[0]<=x<=self.block[1] and self.block[2]<=z<=self.block[3])

    def try_step(self,a,b):
        for t in np.linspace(0,1,20):
            if not self.is_navigable(np.asarray(a)+t*(np.asarray(b)-a)):return np.asarray(a)
        return np.asarray(b)

    def distance_to_closest_obstacle(self,p,cap):
        x,_,z=p
        distance=min(x,self.width-x,z,self.height-z,cap)
        if self.block:
            a,b,c,d=self.block
            distance=min(distance,math.hypot(max(a-x,0,x-b),max(c-z,0,z-d)))
        return max(0,distance)


class ClearanceTests(unittest.TestCase):
    def test_soft_cost_prefers_corridor_interior_and_keeps_exact_endpoints(self):
        pf=RectangleNavMesh()
        seed=[[.17,0,.15],[3.83,0,.15]]
        path,stats=ClearancePlanner(pf,seed,grid_m=.2,padding_m=.2).plan()
        self.assertEqual(path[0],seed[0]);self.assertEqual(path[-1],seed[-1])
        self.assertGreater(max(p[2] for p in path),.4)
        length=validate_reference_path(pf,path,*seed)
        self.assertGreater(length,np.linalg.norm(np.array(seed[1])-seed[0]))
        self.assertLess(stats['reference_vertices'],stats['raw_vertices'])

    def test_soft_clearance_does_not_close_narrow_passage(self):
        pf=RectangleNavMesh(height=.18)
        seed=[[.1,0,.09],[3.9,0,.09]]
        path,_=ClearancePlanner(pf,seed,grid_m=.05,clearance_m=.2,padding_m=.1).plan()
        self.assertGreater(validate_reference_path(pf,path,*seed),3.7)
        self.assertTrue(all(pf.distance_to_closest_obstacle(p,2)<.2 for p in path))

    def test_final_shortcuts_cannot_cross_obstacle(self):
        pf=RectangleNavMesh(height=3.,block=(1.5,2.5,0.,2.))
        seed=[[.5,0,.5],[1.3,0,2.3],[2.7,0,2.3],[3.5,0,.5]]
        path,_=ClearancePlanner(pf,seed,grid_m=.2,padding_m=.1).plan()
        self.assertGreater(max(p[2] for p in path),2.)
        validate_reference_path(pf,path,seed[0],seed[-1])
        with self.assertRaisesRegex(ValueError,'not directly navigable'):
            validate_reference_path(pf,[seed[0],seed[-1]],seed[0],seed[-1])

    def test_disconnected_map_reports_failure_instead_of_old_path_fallback(self):
        pf=RectangleNavMesh(block=(1.5,2.5,0.,2.))
        with self.assertRaisesRegex(ValueError,'no grid route'):
            ClearancePlanner(pf,[[.5,0,1.],[3.5,0,1.]],grid_m=.2,padding_m=.1).plan()

    def test_zero_weight_keeps_shortest_straight_reference(self):
        pf=RectangleNavMesh()
        seed=[[.2,0,.2],[3.8,0,.2]]
        path,_=ClearancePlanner(pf,seed,grid_m=.2,weight=0.,padding_m=.1).plan()
        self.assertAlmostEqual(validate_reference_path(pf,path,*seed),3.6)

    def test_invalid_parameters_and_nonflat_reference_rejected(self):
        for parameters in ({'grid_m':0},{'clearance_m':-1},{'weight':-1},{'padding_m':float('nan')}):
            with self.subTest(parameters=parameters),self.assertRaises(ValueError):
                ClearancePlanner(RectangleNavMesh(),[[0,0,0],[1,0,0]],**parameters)
        with self.assertRaisesRegex(ValueError,'flat'):
            ClearancePlanner(RectangleNavMesh(),[[0,0,0],[1,1,0]])

    def test_existing_output_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'tasks.json';path.write_text('preserve')
            with patch('sys.argv',['prepare_clearance.py','--tasks','unused.json','--out',folder]),self.assertRaises(FileExistsError):
                main()
            self.assertEqual(path.read_text(),'preserve')


if __name__=='__main__':unittest.main()
