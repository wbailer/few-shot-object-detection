
import sys
import os
import flask
import zipfile
import yaml
import subprocess
import shutil
import requests

from PIL import Image
from flask_cors import CORS

from types import SimpleNamespace
from fsdettools.train_fs import train_fs

from multiprocessing import Process


processlist = []
model_store = './docker/model_store'


def package_model(args, manifest):
    """
    Internal helper for the exporting model command line interface.
    """
    model_file = args.model_file
    serialized_file = args.serialized_file
    model_name = args.model_name
    handler = args.handler
    extra_files = args.extra_files
    export_file_path = args.export_path
    requirements_file = args.requirements_file

    try:
        ModelExportUtils.validate_inputs(model_name, export_file_path)
        # Step 1 : Check if .mar already exists with the given model name
        export_file_path = ModelExportUtils.check_mar_already_exists(
            model_name, export_file_path, args.force, args.archive_format
        )

        # Step 2 : Copy all artifacts to temp directory
        artifact_files = {
            "model_file": model_file,
            "serialized_file": serialized_file,
            "handler": handler,
            "extra_files": extra_files,
            "requirements-file": requirements_file,
        }

        model_path = ModelExportUtils.copy_artifacts(model_name, **artifact_files)

        # Step 2 : Zip 'em all up
        ModelExportUtils.archive(
            export_file_path, model_name, model_path, manifest, args.archive_format
        )
        shutil.rmtree(model_path)
        logging.info(
            "Successfully exported model %s to file %s", model_name, export_file_path
        )
    except ModelArchiverError as e:
        logging.error(e)
        sys.exit(1)


def generate_model_archive():
    """
    Generate a model archive file
    :return:
    """

    logging.basicConfig(format="%(levelname)s - %(message)s")
    args = ArgParser.export_model_args_parser().parse_args()
    manifest = ModelExportUtils.generate_manifest_json(args)
    package_model(args, manifest=manifest)


def get_log_path(name):
    return os.path.join(os.getenv("FSDET_ROOT"),'logs',name+'.log')

def training_worker(name,jobfilepath,basemodelfile):

    global model_store

    print("logging to "+get_log_path(name))

    sys.stdout = open(get_log_path(name), "w")
    sys.stderr = sys.stdout

    args = SimpleNamespace(datasetconfig=jobfilepath , ignoreunknown=True, splitfact=-1)

    os.chdir(os.getenv("FSDET_ROOT"))
    
    if os.getenv("MODEL_STORE"):
        model_store = os.getenv("MODEL_STORE")

    # run the training pipeline
    train_fs(args)
    
    # build the archive
    basename = basemodelfile.split('/')
    newmodelname = ''
    for i in range(len(basename)-2):
        if basename[i]=='coco':
            basename[i] = 'fs'
        newmodelname = newmodelname + basename[i]
        newmodelname = newmodelname + '/'
        
    modeldir = '_'.join(basename[-2].split('_')[:-1]) + '_' + name
    
    newmodelname = newmodelname + modeldir + '/' + basename[-1]
    
    # write inference config
    with open("./configs/custom_datasets/"+name+"_config.yml","w") as txtfile:
        txtfile.write("threshold: 0.2\nfsdet_config: faster_rcnn_R_101_FPN_"+name+".yaml\ncustom_dataset: "+name+"\n")

    # make copy of config and adjust relative path
    shutil.copyfile("./configs/custom_datasets/faster_rcnn_R_101_FPN_ft_all_fshot_"+name+".yaml","./configs/custom_datasets/faster_rcnn_R_101_FPN_"+name+".yaml")
       
    subprocess.run("sed -i 's/_BASE_: \"\.\.\//_BASE_: \"/g' ./configs/custom_datasets/faster_rcnn_R_101_FPN_"+name+".yaml",shell=True)
    subprocess.run("sed -i 's/WEIGHTS: \".*\.pth\"/WEIGHTS: \"model_final.pth\"/g' ./configs/custom_datasets/faster_rcnn_R_101_FPN_"+name+".yaml",shell=True)
    subprocess.run("sed -i s/\'/\"/g ./configs/custom_datasets/faster_rcnn_R_101_FPN_"+name+".yaml",shell=True)

    # make copy of config 
    shutil.copyfile(jobfilepath,"./configs/custom_datasets/"+name+"_.yaml")       

    # extract dataset JSON filenames, and fix paths
    datasetinfo = None
    with open(jobfilepath, 'r') as stream:
        datasetinfo = yaml.safe_load(stream)
        basedsname = datasetinfo['base']['trainval']
        shutil.copyfile(basedsname,"./configs/custom_datasets/base_annotations.json")       
        noveldsname = datasetinfo['novel']['data']
        shutil.copyfile(noveldsname,"./configs/custom_datasets/novel_annotations.json")   
        
        datasetinfo['base']['trainval'] = "base_annotations.json"
        datasetinfo['novel']['data'] = "novel_annotations.json"
        if 'trainval' in datasetinfo['novel'].keys():
            del datasetinfo['novel']['trainval']
        if 'test' in datasetinfo['novel'].keys():
            del datasetinfo['novel']['test']
   
    with open("./configs/custom_datasets/"+name+"_.yaml", 'w') as stream:
        yaml.dump(datasetinfo,stream)
     
        
    # build list of need config files
    extrafilelist = [ "./configs/custom_datasets/faster_rcnn_R_101_FPN_"+name+".yaml",
                      "./configs/custom_datasets/"+name+"_config.yml",
                      "/workspace/few-shot-object-detection/configs/Base-RCNN-FPN.yaml",
                      "./configs/custom_datasets/"+name+"_.yaml",
                      "./configs/custom_datasets/base_annotations.json",
                      "./configs/custom_datasets/novel_annotations.json"
                       ]
                      
    extrafilestr = ','.join(extrafilelist)
        
    # build archive
    #print("torch-model-archiver -f --model-name "+name+" --handler ./docker/fsod_handler.py --extra-files "+extrafilestr+ " --export-path "+model_store+" -v 0.1 --serialized-file "+newmodelname)
    #os.system("torch-model-archiver -f --model-name "+name+" --handler ./docker/fsod_handler.py --extra-files "+extrafilestr+ " --export-path "+model_store+" -v 0.1 --serialized-file "+newmodelname)
    subprocess.run("torch-model-archiver -f --model-name "+name+" --handler ./docker/fsod_handler.py --extra-files "+extrafilestr+ " --export-path "+model_store+" -v 0.1 --serialized-file "+newmodelname,shell=True)
    
    # register with torchserve
    # - unregister in case it already exists
    
    #os.system("curl -X DELETE http://localhost:8081/models/"+name)
    subprocess.run("curl -X DELETE http://localhost:8081/models/"+name,shell=True)
    
    #os.system("curl -X POST  \"http://localhost:8081/models?url="+model_store+"/"+name+".mar&name="+name+"\"")
    subprocess.run("curl -X POST  \"http://localhost:8081/models?url="+model_store+"/"+name+".mar&name="+name+"&initial_workers=1\"",shell=True)

    subprocess.run("curl -X PUT  \"http://localhost:8081/models/"+name+"?min_worker=1\"",shell=True)
 
   

def main():
    app = flask.Flask(__name__)
    CORS(app)
    
    def store_file_to_path(relfilename,data,binary=False):
        
        filename = os.path.join(os.getenv("FSDET_ROOT"),relfilename)
        
        relpath = os.path.dirname(filename)
        
        os.makedirs(relpath,exist_ok=True)
        
        print("storing "+filename)
        
        mode = 'w'
        if binary:
            mode = 'wb'

        with open(filename,mode) as f:
            f.write(data)    
        
    @app.route('/store', methods=['POST'])
    def store_file():
        headers = flask.request.headers

        print( "Request headers:\n" + str(headers) )
        """Print posted body to stdout"""

        try: 
            data = flask.request.data.decode('utf-8')

            filename = flask.request.args.get('name')
        
            store_file_to_path(filename,data)

        except Exception as e:
            return flask.Response(response='Failed to store file: '+str(e), status=500)

            
        return flask.Response(status=200)
        
    @app.route('/train', methods=['POST'])
    def train():

        global processlist

        headers = flask.request.headers
       

        print( "Request headers:\n" + str(headers) )
        """Print posted body to stdout"""

        cfg_file_names = []
        cfg_files = []
        img_file_names = []
        img_files = []

        try: 
            cfgzip = flask.request.files['config']              
            file_like_object = cfgzip.stream._file        
            zipfile_ob = zipfile.ZipFile(file_like_object)
            cfg_file_names = zipfile_ob.namelist()
    
            cfg_files = [(zipfile_ob.open(name).read(),name) for name in cfg_file_names]
            
            # check if images have also been provided
            if 'images' in flask.request.files:
                imgzip = flask.request.files['images']              
                file_like_object = imgzip.stream._file        
                zipfile_ob = zipfile.ZipFile(file_like_object)
                img_file_names = zipfile_ob.namelist()
    
                img_files = [(zipfile_ob.open(name).read(),name) for name in img_file_names]                
            
        except Exception as e:
            return flask.Response(response='Failed to parse ZIP file: '+str(e), status=500)

        # check if ensemble learning option is set

        
        ensemble_learning = False
        ensemble_nr_comp = 0
        
        if 'ensemblecomp' in flask.request.form.keys():
            try:
                ensemble_nr_comp = int(flask.request.form['ensemblecomp'])
                if ensemble_nr_comp>0:
                    ensemble_learning = True
                
            except Exception as e:
                print('WARNING: failed to get ensemble learning parameters - proceeding without')
            
            
            
        # process config files
        jsoncontent = '{}'
        jobcfg = {}
        jobfilepath = ''
        basemodelfile = ''
        
        try:
            for cf,cfdata in zip(cfg_file_names,cfg_files):
                if cf.endswith(".yaml"):
                    bn = os.path.basename(cf)
                    jobfilepath = os.path.join('configs','custom_datasets',bn)
                    
                    store_file_to_path(jobfilepath,cfdata[0].decode('utf-8'))
                   
                    jobcfg = yaml.safe_load(cfdata[0].decode('utf-8'))
                elif cf.endswith(".json"):
                    
                    jsoncontent = cfdata
                else:
                    print('file '+cf+' ignored')
         
            # now serialise JSON, as name can be taken from YAML
            target_fn = jobcfg['novel']['data']
            store_file_to_path(target_fn,jsoncontent[0].decode('utf-8'))
            
            basemodelfile = jobcfg['base']['model']
            
        except Exception as e:
            return flask.Response(response='Failed to process config files: '+str(e), status=500)
            
        # store images
        
        try:
            dataroot = jobcfg['novel']['data_dir']
        
            for imf,imfdata in zip(img_file_names,img_files):
                target_fn = os.path.join('datasets',dataroot,imf)
                store_file_to_path(target_fn,imfdata[0],True)
    
            
        except Exception as e:
            return flask.Response(response='Failed to process image files: '+str(e), status=500)            
            
        # clean up processes
        newprocesslist = []
        for p in processlist:
            if p.is_alive():
                newprocesslist.append(p)
                
        processlist = newprocesslist
            
        # start training in own thread

        try: 
            p = Process(target=training_worker, args=(jobcfg['name'],jobfilepath,basemodelfile,))
            processlist.append(p)
            p.start()
        
        except Exception as e:
            return flask.Response(response='Failed to start worker process: '+str(e), status=500)            
           
            
        return flask.Response(response='OK',status=200,mimetype='text/plain')           
    
        
    @app.route('/log', methods=['GET'])
    def get_log():

        args = flask.request.args

        name = args.get('name',type=str,default='')
        lastlines = args.get('tail',type=int,default=0)
        
        logfilename = get_log_path(name)
                
        try:
            lines = []
            with open(logfilename) as f:
                lines = f.readlines()
                                
            flines = lines[-lastlines:]
                        
            logcontent = '\n'.join(flines)
           
        
        except Exception as e:
            return flask.Response(response='Log file not found: '+str(name),status=404)            
        

        return flask.Response(response=logcontent,status=200,mimetype='text/plain')

    def root_dir():  # pragma: no cover
        return os.path.abspath(os.path.dirname(__file__))


    def get_file(filename):  # pragma: no cover
        try:
            src = os.path.join(root_dir(), filename)

            return open(src).read()
        except IOError as exc:
            return str(exc)


    @app.route('/test/<modelname>', methods=['POST'])   
    def test(modelname): 
    
        res = requests.request(  # ref. https://stackoverflow.com/a/36601467/248616
            method          = flask.request.method,
            url             = 'http://localhost:8080/predictions/'+modelname,
            headers         = {k:v for k,v in flask.request.headers if k.lower() != 'host'}, # exclude 'host' header
            data            = flask.request.get_data(),
            cookies         = flask.request.cookies,
            allow_redirects = False,
        ) 
    
        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']  #NOTE we here exclude all "hop-by-hop headers" defined by RFC 2616 section 13.5.1 ref. https://www.rfc-editor.org/rfc/rfc2616#section-13.5.1
        headers          = [
            (k,v) for k,v in res.raw.headers.items()
            if k.lower() not in excluded_headers
        ] 
        
          
        response = flask.Response(res.content, res.status_code, headers)
        return response
        


    @app.route('/', methods=['GET'], defaults={'path': ''} )
    @app.route('/<path:path>', methods=['GET'])
    def get_resource(path):  # pragma: no cover
        mimetypes = {
          ".css": "text/css",
          ".html": "text/html",
          ".js": "application/javascript",
        }
        complete_path = os.path.join(root_dir(), path)
        ext = os.path.splitext(path)[1]
        mimetype = mimetypes.get(ext, "text/html")
        content = get_file(complete_path)
        return flask.Response(content, mimetype=mimetype)
    
    @app.errorhandler(404)
    def handle_404(e):
        # handle all other routes here
        return flask.Response(status=404)          

    retval = app.run(debug=True, host='::', port=3010)
    
    return retval


if __name__ == '__main__':
    sys.exit(main())
