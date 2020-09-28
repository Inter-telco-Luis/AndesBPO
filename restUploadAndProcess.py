from flask import Flask, request
from flask import Response
from flask_restful import Api, Resource, reqparse
from flask import jsonify
from flask_cors import CORS
import numpy as np
import os
from awsService3 import aws_tables
import time
import re

app = Flask(__name__)
api = Api(app)
CORS(app)
cors=CORS(app, resources={
    r"/*":{
        "origin":"*",
        'Access-Control-Allow-Origin': '*'
    }
})

'''
EJEMPLO DE PETICION
curl -d "ef=/home/pdi/Documents/React/OCR/ocr-it/eeff_100/900327563 EEFF IFRS.tif" -X POST http://localhost:1232/path
'''

# 400 Bad Request   
r_400 = Response("Peticion invalida.", status=400)

# 500 Internal Server Error
r_500 = Response("Error interno del servidor", status=500)

class User(Resource):
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument("ef")
        parser.add_argument("DatosArchivo")
        parser.add_argument("name")
        parser.add_argument("data")
        args = parser.parse_args()

        print('\nPARAMETROS ENTRADA:')
        for key,value in args.items():
            print(key + ':', value)
            
        f = request.files['data']
        name = re.sub(r"\s+", "", args['name'])
        f.save(os.path.join("../FilesTemp",name))
        try:
            json = aws_tables('../FilesTemp/'+name)
            #print()
            #json = {'hola':['hola1','hola2']}
            return json
        except Exception as error:
            print('|ERROR|',error)
            return r_500   

api.add_resource(User, "/")

app.run(debug=True, port=1232, host='0.0.0.0')
