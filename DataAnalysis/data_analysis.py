from sqlalchemy import create_engine, Column, Integer, String, BLOB, FLOAT
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
import numpy as np 
import cv2 
import pickle
import matplotlib.pyplot as plt 
import sqlite3 
from sqlalchemy import update
from numpy.linalg import eig, inv
import os
from .combine_images import combine_images_function
import sympy
from tqdm import tqdm
from skimage.feature import graycomatrix, graycoprops
from scipy.stats import kurtosis, skew
from .components import create_dirs, calc_gradient, basis_conversion, calc_arc_length
Base = declarative_base()
class Cell(Base):
    __tablename__ = 'cells'
    id = Column(Integer, primary_key=True)
    cell_id = Column(String)
    label_experiment = Column(String)
    manual_label  = Column(Integer)
    perimeter = Column(FLOAT)
    area = Column(FLOAT)
    img_ph = Column(BLOB) 
    img_fluo1 = Column(BLOB)
    img_fluo2 = Column(BLOB)
    contour = Column(BLOB)
    center_x = Column(FLOAT)
    center_y = Column(FLOAT)
    

def data_analysis(db_name:str = "test.db", image_size:int = 100,out_name:str ="cell",dual_layer_mode:bool = True,single_layer_mode:bool = False):
    ##############################################################
    n = -1
    cell_lengths = []
    agg_tracker = 0
    means = []
    meds = []
    agg_bool = []
    vars = []
    max_intensities = []
    max_int_minus_med = []
    mean_fluo_raw_intensities = []
    skewnesses = []
    kurtosises = []

    """
    二重染色用データ
    """
    mean_fluo_raw_intensities_2 = []

    """
    テクスチャ解析パラメータ
    """
    energies = []
    contrasts = []
    dice_similarities = []
    homogeneities = []
    correlations = []
    ASMs = []
    smoothnesses = []

    """
    ヒストグラム解析パラメータ
    """
    cumulative_frequencys = []
    ##############################################################
    
    create_dirs(["Cell","Cell/ph","Cell/fluo1","Cell/fluo2","Cell/histo","Cell/histo_cumulative","Cell/replot","Cell/replot_map","Cell/fluo1_incide_cell_only","Cell/fluo2_incide_cell_only","Cell/gradient_magnitudes","Cell/GLCM"])

    engine = create_engine(f'sqlite:///{db_name}', echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as session:
        cells = session.query(Cell).all()
       
        for cell in tqdm(cells):
            if  cell.manual_label != "N/A" and cell.manual_label!= None:
                print("###############################################")
                print(cell.cell_id)
                print("###############################################")
                n+=1

                """
                Load image
                """
                image_ph = cv2.imdecode(np.frombuffer(cell.img_ph, dtype=np.uint8), cv2.IMREAD_COLOR)
                image_ph_copy = image_ph.copy()
                cv2.drawContours(image_ph_copy,pickle.loads(cell.contour),-1,(0,255,0),1)
                position = (0, 15)  
                font = cv2.FONT_HERSHEY_SIMPLEX
                font_scale = 0.5 
                font_color = (255, 255, 255)  
                thickness = 1 
                cv2.putText(image_ph, f"{cell.cell_id}", position, font, font_scale, font_color, thickness)
                cv2.imwrite(f"Cell/ph/{n}.png",image_ph_copy)


                cell_contour = [list(i[0]) for i in pickle.loads(cell.contour)]
                print(cell_contour)

                coords_inside_cell_1,  points_inside_cell_1 = [], []
                coords_inside_cell_2,  points_inside_cell_2 = [], []
                if not single_layer_mode:
                    image_fluo1 = cv2.imdecode(np.frombuffer(cell.img_fluo1, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
                    fluo_out1 = cv2.imdecode(np.frombuffer(cell.img_fluo1, dtype=np.uint8), cv2.IMREAD_COLOR)
                    cv2.drawContours(fluo_out1,pickle.loads(cell.contour),-1,(0,0,255),1)
                    cv2.imwrite(f"Cell/fluo1/{n}.png",fluo_out1)
                    output_image =  np.zeros((image_size,image_size),dtype=np.uint8)
                    # cv2.drawContours(output_image, [pickle.loads(cell.contour)], 0, 255, thickness=cv2.FILLED)
                    for i in range(image_size):
                        for j in range(image_size):
                            if cv2.pointPolygonTest(pickle.loads(cell.contour), (j,i), False)>=0:
                                output_image[i][j] = image_fluo1[i][j]
                                
                    cv2.imwrite(f"Cell/fluo1_incide_cell_only/{n}.png",output_image)

                if dual_layer_mode:
                    image_fluo2 = cv2.imdecode(np.frombuffer(cell.img_fluo2, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
                    fluo_out2 = cv2.imdecode(np.frombuffer(cell.img_fluo2, dtype=np.uint8), cv2.IMREAD_COLOR)
                    cv2.drawContours(fluo_out2,pickle.loads(cell.contour),-1,(0,0,255),1)
                    cv2.imwrite(f"Cell/fluo2/{n}.png",fluo_out2)

                    output_image =  np.zeros((image_size,image_size),dtype=np.uint8)
                    # cv2.drawContours(output_image, [pickle.loads(cell.contour)], 0, 255, thickness=cv2.FILLED)

                    for i in range(image_size):
                        for j in range(image_size):
                            if cv2.pointPolygonTest(pickle.loads(cell.contour), (j,i), False)>=0:
                                output_image[i][j] = image_fluo2[i][j]
                                
                    cv2.imwrite(f"Cell/fluo2_incide_cell_only/{n}.png",output_image)


                if not single_layer_mode:
                    ############################以下勾配計算##################################
                    # Sobelフィルタを適用してX方向の勾配を計算
                    sobel_x = cv2.Sobel(output_image, cv2.CV_64F, 1, 0, ksize=3)

                    # Sobelフィルタを適用してY方向の勾配を計算
                    sobel_y = cv2.Sobel(output_image, cv2.CV_64F, 0, 1, ksize=3)

                    # 勾配の合成（勾配強度と角度を計算）
                    gradient_magnitude = np.sqrt(sobel_x**2 + sobel_y**2)

                    # 勾配の強度を正規化
                    # gradient_magnitude = cv2.normalize(gradient_magnitude, None, 0, 255, cv2.NORM_MINMAX, cv2.CV_8U)

                    # 勾配強度画像を保存
                    cv2.imwrite(f'Cell/gradient_magnitudes/gradient_magnitude{n}.png', gradient_magnitude)


                if True:
                    if not single_layer_mode:
                        for i in range(image_size):
                            for j in range(image_size):
                                if cv2.pointPolygonTest(pickle.loads(cell.contour), (i,j), False)>=0:
                                    coords_inside_cell_1.append([i,j])
                                    points_inside_cell_1.append(output_image[j][i])
                    if single_layer_mode:
                        for i in range(image_size):
                            for j in range(image_size):
                                if cv2.pointPolygonTest(pickle.loads(cell.contour), (i,j), False)>=0:
                                    coords_inside_cell_1.append([i,j])
                    if dual_layer_mode:
                        for i in range(image_size):
                            for j in range(image_size):
                                if cv2.pointPolygonTest(pickle.loads(cell.contour), (i,j), False)>=0:
                                    coords_inside_cell_2.append([i,j])
                                    points_inside_cell_2.append(image_fluo2[j][i])
                    # Basis conversion
                    contour = [[j,i] for i,j in [i[0] for i in pickle.loads(cell.contour)]]
                    X = np.array([[i[1] for i in coords_inside_cell_1],[i[0] for i in coords_inside_cell_1]])

                    u1,u2,u1_contour,u2_contour,min_u1,max_u1,u1_c,u2_c,U,contour_U = basis_conversion(contour,X,cell.center_x,cell.center_y,coords_inside_cell_1)
                    min_u1, max_u1 = min(u1), max(u1)
                    fig = plt.figure(figsize=[6,6])
                    cmap = plt.get_cmap('inferno')
                    x = np.linspace(0,100,1000)
                    if not single_layer_mode:
                        max_points = max(points_inside_cell_1)
                        plt.scatter(u1,u2,c =[i/max_points for i in points_inside_cell_1],s = 10,cmap=cmap )
                        plt.scatter(u1_contour,u2_contour,s = 10,color = "lime" )
                        plt.grid()

                    W = np.array([[i**4,i**3,i**2,i,1] for i in [i[1] for i in U]])
                    f = np.array([i[0] for i in U])
                    theta = inv(W.transpose()@W)@W.transpose()@f
                    x = np.linspace(min_u1,max_u1,1000)
                    y = [theta[0]*i**4+theta[1]*i**3 + theta[2]*i**2+theta[3]*i + theta[4] for i in x]

                    cell_length = calc_arc_length(theta,min_u1,max_u1)
                    print(cell_lengths)
                    cell_lengths.append([cell.cell_id,cell_length])

                    plt.plot(x,y,color = "blue",linewidth=1)
                    plt.scatter(min_u1,theta[0]*min_u1**4+theta[1]*min_u1**3 + theta[2]*min_u1**2+theta[3]*min_u1 + theta[4],s = 100,color = "red",zorder = 100,marker = "x")
                    plt.scatter(max_u1,theta[0]*max_u1**4+theta[1]*max_u1**3 + theta[2]*max_u1**2+theta[3]*max_u1 + theta[4],s = 100,color = "red",zorder = 100,marker = "x")
                    plt.xlim(min_u1-40,max_u1+40)
                    plt.ylim(u2_c-40,u2_c+40)
                    plt.xlabel("u1")
                    plt.ylabel("u2")
                    plt.axis("equal")

                    normalized_points = [i/max_points for i in points_inside_cell_1]

                    #######################################################統計データ#######################################################
                    med = sorted(normalized_points)[len(normalized_points)//2]
                    med_raw = sorted(points_inside_cell_1)[len(points_inside_cell_1)//2]
                    meds.append(med)
                    means.append(sum(normalized_points)/len(normalized_points))
                    vars.append(np.var(normalized_points))
                    max_intensities.append(max_points)
                    max_int_minus_med.append(max_points-med_raw)
                    mean_fluo_raw_intensities.append(sum(points_inside_cell_1)/len(points_inside_cell_1))
                    if dual_layer_mode:
                        mean_fluo_raw_intensities_2.append(sum(points_inside_cell_2)/len(points_inside_cell_2))
                    #######################################################統計データ#######################################################
                    plt.text(u1_c,u2_c+25,s=f"Mean:{round(sum(normalized_points)/len(normalized_points),3)}\nMed:{round(sorted(normalized_points)[len(normalized_points)//2],3)}\nCell length(μm):{round(cell_length*0.0625,2)}",color = "red",ha="center",va="top")
                    
                    # if med < 0.7:
                    #     plt.scatter(u1_c,u2_c-30,s = 150,color = "red",zorder = 100)
                    #     agg_tracker += 1
                    #     agg_bool.append(1)
                    # else:
                    #     agg_bool.append(0)
                    fig.savefig(f"Cell/replot/{n}.png")
                    plt.close()

                    #######################################################ヒストグラム解析#######################################################
                    """
                    正規化した細胞内輝度によるヒストグラムの描画
                    """
                    fig_histo = plt.figure(figsize=[6,6])
                    plt.hist(points_inside_cell_1,bins=100)
                    plt.xlim(0,255)
                    plt.xlabel("Fluo. intensity")
                    plt.ylabel("Frequency")
                    plt.grid()
                    fig_histo.savefig(f"Cell/histo/{n}.png")
                    plt.close()
                    # data = [i/255 for i in points_inside_cell_1]
                    # skewness = skew(data)
                    # kurtosis_ = kurtosis(data)
                    # skewnesses.append(skewness)
                    # kurtosises.append(kurtosis_)

                    #######################################################ヒストグラム解析（累積頻度）#######################################################

                    fig_histo_cumulative = plt.figure(figsize=[6,6])
                    plt.hist(normalized_points,bins=100,cumulative=True)
                    # 0から255までの頻度を計算
                    frequency = np.bincount(points_inside_cell_1, minlength=256)
                    # 累積頻度の計算
                    cumulative_frequency = np.cumsum(frequency)
                    cumulative_frequency = cumulative_frequency / cumulative_frequency[-1]
                    cumulative_frequencys.append(cumulative_frequency)
                    plt.plot(cumulative_frequency)
                    plt.title('Cumulative Frequency Plot')
                    plt.xlabel('Value (0 to 255)')
                    plt.ylabel('Cumulative Frequency')
                    plt.xlim(-10, 255)
                    plt.ylim(0, 1.05)
                    plt.grid(True)
                    fig_histo_cumulative.savefig(f"Cell/histo_cumulative/{n}.png")
                    plt.close()

    total_rows = int(np.sqrt(n))
    total_cols = total_rows + 1
    num_images = n
    filename = db_name[:-3]
    combine_images_function(total_rows, total_cols, image_size, num_images, out_name,single_layer_mode, dual_layer_mode)

    fig_histo_cumulative_inOne = plt.figure(figsize=[6,6])
    for cumulative_freq in cumulative_frequencys:
        plt.plot(cumulative_freq)
        print(cumulative_freq)
    plt.title('Cumulative Frequency Plot')
    plt.xlabel('Value (0 to 255)')
    plt.ylabel('Cumulative Frequency')
    plt.xlim(-10, 255)
    plt.ylim(0, 1.05)
    plt.grid(True)
    fig_histo_cumulative_inOne.savefig(f"{filename}_cumulative_frequency_one.png")
    with open(f"{filename}_cumulative_frequency_one.txt",mode="w") as fpout:
        for i in cumulative_frequencys:
                fpout.write(f"{','.join([str(float(i)) for i in i])}\n")
    # with open(f"{out_name}_cell_lengths.txt",mode="w") as fpout:
    #     for i in cell_lengths:
    #         fpout.write(f"{i[0]},{i[1]}\n")

    # with open(f"{out_name}_agg_formation_rate.txt",mode="w") as fpout:
    #     fpout.write(f"out_name,num_agg_detected,num_total_cells,agg_form_rate\n")
    #     fpout.write(f"{out_name},{agg_tracker},{n},{agg_tracker/n}\n")
    # with open(f"{out_name}_meds_means_vars.txt",mode="w") as fpout:
    #     for i in range(len(meds)):
    #         fpout.write(f"{meds[i]},{means[i]},{vars[i]}\n")
    # with open(f"{out_name}_fluo_2_mean_fluo_intensities.txt",mode="w") as fpout:
    #     for i in range(len(mean_fluo_raw_intensities_2)):
    #         fpout.write(f"{mean_fluo_raw_intensities_2[i]}\n")

    # with open(f"{out_name}_max_int_minus_med.txt",mode="w") as fpout:
    #     for i in range(len(meds)):
    #         fpout.write(f"{max_int_minus_med[i]}\n")
    # with open(f"{out_name}_mean_fluo_raw_intensities.txt",mode="w") as fpout:
    #     for i in range(len(meds)):
    #         fpout.write(f"{mean_fluo_raw_intensities[i]}\n")

    # with open(f"{out_name}_energies.txt",mode="w") as fpout:
    #     for i in range(len(energies)):
    #         fpout.write(f"{energies[i][0][0]}\n")
    # with open(f"{out_name}_contrasts.txt",mode="w") as fpout:
    #     for i in range(len(contrasts)):
    #         fpout.write(f"{contrasts[i][0][0]}\n")
    
    # with open(f"{out_name}_dice_similarities.txt",mode="w") as fpout:
    #     for i in range(len(dice_similarities)):
    #         fpout.write(f"{dice_similarities[i]}\n")
    
    # with open(f"{out_name}_homogeneities.txt",mode="w") as fpout:
    #     for i in range(len(homogeneities)):
    #         fpout.write(f"{homogeneities[i][0][0]}\n")
        
    # with open(f"{out_name}_correlations.txt",mode="w") as fpout:
    #     for i in range(len(correlations)):
    #         fpout.write(f"{correlations[i][0][0]}\n")
    
    # with open(f"{out_name}_ASMs.txt",mode="w") as fpout:
    #     for i in range(len(ASMs)):
    #         fpout.write(f"{ASMs[i][0][0]}\n")
    
    # with open(f"{out_name}_smoothnesses.txt",mode="w") as fpout:
    #     for i in range(len(smoothnesses)):
    #         fpout.write(f"{smoothnesses[i]}\n")

    # with open(f"{out_name}_skewnesses.txt",mode="w") as fpout:
    #     for i in range(len(skewnesses)):
    #         fpout.write(f"{skewnesses[i]}\n")

    # with open(f"{out_name}_kurtosises.txt",mode="w") as fpout:
    #     for i in range(len(kurtosises)):
    #         fpout.write(f"{kurtosises[i]}\n")
    
    





        








