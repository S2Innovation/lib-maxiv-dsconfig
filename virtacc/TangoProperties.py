TANGO_PROPERTIES = {
    'Magnet' : [
        {                                                 #Properties deduced from lattice or filled later
            'Energy':[0.0], 
            'Circuit':[''], 
            #'IsCircuit':[''], 
            #''Sisters':[], 
            'Type':[''], 
        },     
        {
            'l':'Length',                                 #Property read direct from lattice
             #'k1':'DYNAMIC_PROPERTIES:k1=float(XXX)',      #This becomes an attribute for kquad
             #'angle':'DYNAMIC_PROPERTIES:angle=float(XXX)' #This becomes an attribute for dipole
        }         
        ],
    'VAYAGScreen' : [
        {},    
        {
            'filename':'image'
        }   
        ]                    

    }
